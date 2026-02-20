#!/usr/bin/env python3
"""
Parse Student_Timetables Version Ramazan.pdf and update schedules_index.json.
Uses pdftotext -layout for structured extraction.
"""
import re
import json
import subprocess
from pathlib import Path

TIME_SLOTS = [
    ("8:00", "9:05"),
    ("9:10", "10:15"),
    ("10:20", "11:25"),
    ("11:30", "12:35"),
    ("12:40", "1:45"),
    ("2:00", "3:05"),
    ("3:10", "4:15"),
    ("4:15", "5:10"),
]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

# Teacher (Room) pattern
TEACHER_RE = re.compile(r"^([A-Za-z][A-Za-z\.\-\s]+?)\s*\(([^)]+)\)\s*$")
# Course code start
COURSE_RE = re.compile(r"([A-Z]{2,4}\d{4}[^\(]*)")


def extract_text(pdf_path: str) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")
    return result.stdout


def parse_timetable_blocks(text: str) -> list[tuple[str, str]]:
    """Split text into (roll_number, block_text) pairs."""
    blocks = []
    pattern = re.compile(r"Timetable for (\d+P-\d+)\s*\n", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        roll = m.group(1).strip().upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        blocks.append((roll, block))
    return blocks


def get_column_positions(header_line: str) -> list[int]:
    """Extract approximate start position of each time slot column from header."""
    markers = ["8:00-9:05", "9:10-10:15", "10:20-11:25", "11:30-12:35",
               "12:40-1:45", "2:00-3:05", "3:10-4:15", "4:15-5:10"]
    positions = []
    for m in markers:
        pos = header_line.find(m)
        if pos >= 0:
            positions.append(pos)
    if len(positions) < 5:
        positions = list(range(0, 200, 25))[:8]
    return positions


def pos_to_column(indent: int, positions: list[int]) -> int:
    """Map character position to column index (0-7)."""
    for i in range(len(positions) - 1):
        if positions[i] <= indent < positions[i + 1]:
            return i
    if positions and indent >= positions[-1]:
        return len(positions) - 1
    return 0


def parse_block(block: str) -> list[dict]:
    """Parse a single student timetable block into class sessions."""
    sessions = []
    lines = [l for l in block.split("\n") if l.strip()]

    header_line = None
    for line in lines:
        if "8:00-9:05" in line:
            header_line = line
            break
    if not header_line:
        return sessions

    positions = get_column_positions(header_line)
    if not positions:
        return sessions

    current_day = None
    pending = []  # [(col, subject_parts, teacher, room), ...]
    subject_fixes = {
        "Proces...": "Processing",
        "Distrib...": "Distributed Computing",
        "Comput...": "Computing",
        "Comp...": "Computing",
        "of Soft...": "of Software Project Management",
        "Intellige...": "Intelligence",
        "Machine Lear...": "Machine Learning",
        "an...": "and Simulation",
    }

    def add_session(day: str, col: int, subject, teacher: str, room: str):
        if isinstance(subject, list):
            subject = " ".join(str(p) for p in subject).strip()
        if col >= len(TIME_SLOTS) or not subject or not re.search(r"[A-Z]{2,4}\d{4}", str(subject)):
            return
        subject = re.sub(r"\s+", " ", subject).strip()
        for old, new in subject_fixes.items():
            subject = subject.replace(old, new)
        subject = re.sub(r"\s*\.\.\.\s*$", "", subject)
        if subject:
            start, end = TIME_SLOTS[col]
            sessions.append({
                "day": day,
                "start_time": start,
                "end_time": end,
                "subject": subject,
                "room": room or "TBA",
                "teacher": teacher or "",
            })

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        day_match = re.match(r"^(Mon|Tue|Wed|Thu|Fri)\s*", line)
        indent = len(line) - len(line.lstrip())

        if day_match:
            day = day_match.group(1)
            if current_day and pending:
                for col, parts, tch, rm in pending:
                    subj = " ".join(parts).strip() if isinstance(parts, list) else str(parts)
                    add_session(current_day, col, subj, tch, rm)
                pending = []
            current_day = day
            rest = line[len(day_match.group(0)):].strip()
            if rest:
                tch_m = TEACHER_RE.match(rest)
                if tch_m:
                    col = pos_to_column(indent + len(day_match.group(0)), positions)
                    subj_m = COURSE_RE.search(rest)
                    subj = subj_m.group(1).strip() if subj_m else ""
                    if subj:
                        add_session(day, col, subj, tch_m.group(1).strip(), tch_m.group(2).strip())
            i += 1
            continue

        if current_day is None:
            i += 1
            continue

        tch_m = TEACHER_RE.match(stripped)
        if tch_m:
            col = pos_to_column(indent, positions)
            teacher = tch_m.group(1).strip()
            room = tch_m.group(2).strip()
            subj = ""
            if pending:
                for (pc, parts, _, _) in pending:
                    if pc == col:
                        subj = " ".join(parts).strip()
                        break
            if not subj and i > 0:
                prev = lines[i - 1].strip()
                subj_m = COURSE_RE.search(prev)
                if subj_m:
                    subj = subj_m.group(1).strip()
            if subj:
                add_session(current_day, col, subj, teacher, room)
            pending = [(c, p, t, r) for (c, p, t, r) in pending if c != col]
            i += 1
            continue

        subj_m = COURSE_RE.search(stripped)
        if subj_m and not tch_m:
            col = pos_to_column(indent, positions)
            subj = subj_m.group(1).strip()
            if subj and "(" not in stripped:
                if i + 1 < len(lines):
                    next_stripped = lines[i + 1].strip()
                    next_tch = TEACHER_RE.match(next_stripped)
                    if next_tch:
                        add_session(current_day, col, subj, next_tch.group(1).strip(), next_tch.group(2).strip())
                        i += 2
                        continue
                pending.append((col, [subj], "", ""))
        else:
            for j, (c, parts, t, r) in enumerate(pending):
                if stripped and not TEACHER_RE.match(stripped) and re.search(r"[A-Za-z0-9\-\s]", stripped):
                    parts.append(stripped)
                    pending[j] = (c, parts, t, r)
                    break
        i += 1

    if current_day and pending:
        for col, parts, tch, rm in pending:
            subj = " ".join(parts).strip()
            if subj and tch:
                add_session(current_day, col, subj, tch, rm)

    return sessions


def parse_pdf(pdf_path: str) -> dict:
    text = extract_text(pdf_path)
    blocks = parse_timetable_blocks(text)
    result = {}
    for roll, block in blocks:
        sessions = parse_block(block)
        seen = set()
        unique = []
        for s in sessions:
            k = (s["day"], s["start_time"], s["subject"][:50])
            if k not in seen:
                seen.add(k)
                unique.append(s)
        result[roll] = {
            "roll_number": roll,
            "weekly_schedule": unique,
            "exam_schedule": [],
        }
    return result


def main():
    base = Path(__file__).resolve().parent.parent
    pdf_path = base.parent / "Student_Timetables Version Ramazan.pdf"
    index_path = base / "api" / "schedules_index.json"

    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return 1

    print(f"Parsing {pdf_path}...")
    parsed = parse_pdf(str(pdf_path))
    total_classes = sum(len(d["weekly_schedule"]) for d in parsed.values())
    print(f"Parsed {len(parsed)} students, {total_classes} total class sessions")

    existing = {"exam_type": "Sessional I", "schedules": {}}
    if index_path.exists():
        with open(index_path) as f:
            existing = json.load(f)

    for roll, data in parsed.items():
        old = existing.get("schedules", {}).get(roll, {})
        exam = old.get("exam_schedule", [])
        existing["schedules"][roll] = {
            "roll_number": roll,
            "weekly_schedule": data["weekly_schedule"],
            "exam_schedule": exam,
        }

    with open(index_path, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"Updated {index_path}")
    return 0


if __name__ == "__main__":
    exit(main())
