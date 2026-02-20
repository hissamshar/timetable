#!/usr/bin/env python3
"""
Parse Student_Timetables Version Ramazan.pdf and update schedules_index.json.
- Uses pdftotext -layout for grid structure
- Splits merged courses by course code
- Resolves teacher names from faculty_data.json
- Expands course names from exam_schedule data
- Normalizes rooms via metadata.json
- Arranges output by course code, day, time
"""
import re
import json
import subprocess
from pathlib import Path
from typing import Optional

# Ramazan time slots
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

# Course code pattern: CS2005, MT2005, CL2005, etc. Matches CODE,SECTION: only.
COURSE_CODE_RE = re.compile(r"([A-Z]{2,4}\d{4})(?:,([A-Za-z0-9\-]+))?:\s*")
# Match next course code (for splitting) - used to bound subject text
NEXT_COURSE_RE = re.compile(r"(?=[A-Z]{2,4}\d{4}[,\s:])")
# Teacher (Room) - for stripping from text (matches any in string)
TEACHER_ROOM_RE = re.compile(r"([A-Za-z][A-Za-z\.\s\-]+?)\s*\(([^)]+)\)")
# Teacher line - whole line is "Name (Venue)"
TEACHER_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z\.\s\-]+?)\s*\(([^)]+)\)\s*$")
# Truncation suffixes to expand
TRUNCATION_MAP = {
    "Proces...": "Processing",
    "Distrib...": "Distributed Computing",
    "Comput...": "Computing",
    "Comp...": "Computing",
    "of Soft...": "of Software Project Management",
    "Intellige...": "Intelligence",
    "Machine Lear...": "Machine Learning",
    "an...": "and Simulation",
    "Soft...": "Software Project Management",
    "L...": "Lab",
    "and Stat...": "and Statistics",
    "Stat...": "Statistics",
}


def load_project_data(base: Path) -> tuple[dict, dict, dict, dict]:
    """Load course map, faculty, metadata, existing schedules."""
    course_map = {}
    faculty_names = {}
    room_aliases = {}
    existing = {"schedules": {}}

    # Course names from exam_schedule
    index_path = base / "api" / "schedules_index.json"
    if index_path.exists():
        with open(index_path) as f:
            existing = json.load(f)
        for sched in existing.get("schedules", {}).values():
            for e in sched.get("exam_schedule", []):
                subj = e.get("subject", "")
                if " - " in subj:
                    code, name = subj.split(" - ", 1)
                    code = code.strip()
                    if code and re.match(r"^[A-Z]{2,4}\d{4}$", code):
                        course_map[code] = name.strip()

    # Faculty: build fuzzy name lookup (PDF name -> canonical name)
    faculty_path = base / "api" / "faculty_data.json"
    if faculty_path.exists():
        with open(faculty_path) as f:
            faculty = json.load(f)
        for f_ in faculty:
            name = f_.get("name", "")
            if not name:
                continue
            # Key by last significant part: "Ali Sayyed", "Omar Usman Khan"
            parts = name.replace("Dr.", "").replace("Mr.", "").replace("Ms.", "").strip().split()
            for variant in [name, " ".join(parts)]:
                key = variant.lower().replace("-", " ").strip()
                faculty_names[key] = name
            # Also key by "FirstName LastName" abbreviations: "M Tahir" -> "Dr. Muhammad Tahir"
            if len(parts) >= 2:
                short = f"{parts[0][0]} {parts[-1]}"  # M Tahir
                faculty_names[short.lower()] = name
                faculty_names[f"{parts[-1]} {parts[0][0]}".lower()] = name

    # Metadata: room aliases + teachers (for names not in faculty_data)
    meta_path = base / "api" / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)
        room_aliases = meta.get("room_aliases", {})
        for t in meta.get("teachers", []):
            s = t.strip() if isinstance(t, str) else ""
            if len(s) > 4 and s[0].isalpha() and not any(c.isdigit() for c in s):
                faculty_names[s.lower()] = s

    return course_map, faculty_names, room_aliases, existing


def resolve_teacher(raw: str, faculty_names: dict) -> str:
    """Resolve PDF teacher name to faculty_data canonical name."""
    raw = raw.strip()
    if not raw:
        return ""
    # Clean: remove day names that leaked
    raw = re.sub(r"\b(Mon|Tue|Wed|Thu|Fri)\b", "", raw).strip()
    if not raw:
        return ""
    key = raw.lower().replace("-", " ")
    if key in faculty_names:
        return faculty_names[key]
    # Try without first initial
    parts = raw.split()
    if len(parts) >= 2 and len(parts[0]) == 1:
        key2 = " ".join(parts[1:]).lower()
        for k, v in faculty_names.items():
            if key2 in k or k.endswith(key2):
                return v
    # Fuzzy: last name match
    last = parts[-1].lower() if parts else ""
    for k, v in faculty_names.items():
        if k.endswith(last) or last in k.split():
            return v
    return raw


def normalize_room(raw: str, room_aliases: dict) -> str:
    """Normalize room via metadata aliases."""
    raw = (raw or "").strip()
    if not raw:
        return "TBA"
    key = raw.lower().strip()
    if key in room_aliases:
        return room_aliases[key]
    key2 = key.replace(" ", "")
    if key2 in room_aliases:
        return room_aliases[key2]
    if re.match(r"^room\s*\d+", raw, re.I):
        return raw.title()
    return raw


def expand_course_name(code: str, section: str, partial: str, course_map: dict) -> str:
    """Build full subject: CODE,SECTION: Full Name."""
    partial = partial.strip()
    for old, new in TRUNCATION_MAP.items():
        partial = partial.replace(old, new)
    partial = re.sub(r"\s*\.\.\.\s*$", "", partial)
    if partial.endswith(" - ") and code.startswith("CL"):
        partial = partial + "Lab"
    full_name = course_map.get(code, partial)
    prefix = f"{code},{section}: " if section else f"{code}: "
    return prefix + full_name


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
    """Split into (roll_number, block_text) pairs."""
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


def get_column_positions(header: str) -> list[int]:
    markers = ["8:00-9:05", "9:10-10:15", "10:20-11:25", "11:30-12:35",
               "12:40-1:45", "2:00-3:05", "3:10-4:15", "4:15-5:10"]
    positions = [header.find(m) for m in markers if header.find(m) >= 0]
    if len(positions) < 5:
        positions = list(range(0, 240, 30))[:8]
    return sorted(positions)


def pos_to_column(pos: int, positions: list[int]) -> int:
    for i in range(len(positions) - 1):
        if positions[i] <= pos < positions[i + 1]:
            return i
    if positions and pos >= positions[-1]:
        return min(len(positions) - 1, len(TIME_SLOTS) - 1)
    return 0


def parse_block(
    block: str,
    course_map: dict,
    faculty_names: dict,
    room_aliases: dict,
) -> list[dict]:
    """Parse one student block into class sessions."""
    sessions = []
    lines = block.split("\n")

    header_idx = None
    for idx, ln in enumerate(lines):
        if "8:00-9:05" in ln:
            header_idx = idx
            break
    if header_idx is None:
        return sessions

    header_line = lines[header_idx]
    positions = get_column_positions(header_line)
    current_day: Optional[str] = None
    # Content appearing before day label (first cell of first row)
    pre_day_buffer: dict[int, list[str]] = {}
    # Per-column: [(subject_parts, teacher, room)]
    col_buffers: dict[int, list[tuple[list[str], str, str]]] = {}

    def clean_and_extract_courses(text: str) -> list[tuple[str, str, str]]:
        """Strip teacher/room clutter, split by course code, return (code, section, partial) per course."""
        # Remove all "Name (Venue)" chunks - they clutter the subject
        cleaned = TEACHER_ROOM_RE.sub(" ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        result = []
        for m in COURSE_CODE_RE.finditer(cleaned):
            code = m.group(1)
            section = m.group(2) or ""
            start = m.end()
            # Find end: next course code or end
            next_m = COURSE_CODE_RE.search(cleaned, start)
            end = next_m.start() if next_m else len(cleaned)
            partial = cleaned[start:end].strip()
            if partial or code:
                result.append((code, section, partial))
        return result

    def flush_cell(day: str, col: int, subject_parts: list[str], teacher: str, room: str):
        if col >= len(TIME_SLOTS) or not day:
            return
        text = " ".join(subject_parts).strip()
        if not text:
            return
        courses = clean_and_extract_courses(text)
        if not courses:
            return
        tch = resolve_teacher(teacher, faculty_names)
        rm = normalize_room(room, room_aliases)
        for code, section, partial in courses:
            subj = expand_course_name(code, section, partial, course_map)
            start, end = TIME_SLOTS[col]
            sessions.append({
                "day": day,
                "start_time": start,
                "end_time": end,
                "subject": subj,
                "room": rm,
                "teacher": tch,
            })

    def flush_buffers():
        for col, items in col_buffers.items():
            for parts, tch, rm in items:
                if current_day and parts:
                    flush_cell(current_day, col, parts, tch, rm)
        col_buffers.clear()

    def merge_pre_day_into_buffers():
        for col, parts in pre_day_buffer.items():
            if parts:
                col_buffers.setdefault(col, []).append((parts, "", ""))
        pre_day_buffer.clear()

    i = header_idx + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        day_match = re.match(r"^(Mon|Tue|Wed|Thu|Fri)\s*", line)

        if day_match:
            # Merge pre-day content into buffers (content before this day label)
            merge_pre_day_into_buffers()
            current_day = day_match.group(1)
            rest = line[len(day_match.group(0)):].strip()
            # Content on same line as day (e.g. "Security" continuation)
            if rest:
                tch_m = TEACHER_LINE_RE.match(rest)
                rest_col = pos_to_column(indent + len(day_match.group(0)), positions)
                if tch_m:
                    for code, section, partial in clean_and_extract_courses(rest):
                        subj = expand_course_name(code, section, partial, course_map)
                        flush_cell(current_day, rest_col, [subj], tch_m.group(1), tch_m.group(2))
                else:
                    # Append continuation to existing buffer for this col
                    if col_buffers.get(rest_col):
                        col_buffers[rest_col][-1][0].append(rest)
                    else:
                        col_buffers.setdefault(rest_col, []).append(([rest], "", ""))
            i += 1
            continue

        col = pos_to_column(indent, positions)
        tch_m = TEACHER_LINE_RE.match(stripped)

        if tch_m:
            teacher, room = tch_m.group(1), tch_m.group(2)
            if current_day is None:
                # Teacher before any day - use Mon (first row)
                if pre_day_buffer:
                    k = min(pre_day_buffer.keys())
                    parts = pre_day_buffer.pop(k, [])
                    if parts:
                        flush_cell("Mon", k, parts, teacher, room)
            elif col_buffers.get(col):
                parts, _, _ = col_buffers[col].pop()
                if parts:
                    flush_cell(current_day, col, parts, teacher, room)
            else:
                if i > 0:
                    prev = lines[i - 1].strip()
                    for code, section, partial in clean_and_extract_courses(prev):
                        subj = expand_course_name(code, section, partial, course_map)
                        flush_cell(current_day, col, [subj], teacher, room)
                        break
            i += 1
            continue

        # Subject/course line
        for code, section, partial in clean_and_extract_courses(stripped):
            blob = f"{code},{section}: {partial}".strip(", :")
            if current_day is None:
                pre_day_buffer.setdefault(col, []).append(blob)
            else:
                col_buffers.setdefault(col, []).append(([blob], "", ""))
                if i + 1 < len(lines):
                    next_ln = lines[i + 1].strip()
                    if TEACHER_LINE_RE.match(next_ln):
                        pass  # Will be handled next iteration
            break
        else:
            if stripped and not tch_m:
                if current_day is None and pre_day_buffer:
                    # Continuation of pre-day content - append to first col
                    k = min(pre_day_buffer.keys())
                    pre_day_buffer[k].append(stripped)
                elif col in col_buffers and col_buffers[col]:
                    last_parts, t, r = col_buffers[col][-1]
                    last_parts.append(stripped)
        i += 1

    flush_buffers()

    # Deduplicate and sort by course code, day, time
    seen = set()
    unique = []
    for s in sessions:
        k = (s["day"], s["start_time"], s["subject"][:60])
        if k not in seen:
            seen.add(k)
            unique.append(s)
    day_order = {d: i for i, d in enumerate(DAYS)}
    unique.sort(key=lambda x: (x["subject"][:10], day_order.get(x["day"], 99), x["start_time"]))
    return unique


def parse_pdf(
    pdf_path: str,
    course_map: dict,
    faculty_names: dict,
    room_aliases: dict,
) -> dict:
    text = extract_text(pdf_path)
    blocks = parse_timetable_blocks(text)
    result = {}
    for roll, block in blocks:
        sessions = parse_block(block, course_map, faculty_names, room_aliases)
        result[roll] = {
            "roll_number": roll,
            "weekly_schedule": sessions,
            "exam_schedule": [],
        }
    return result


def main() -> int:
    base = Path(__file__).resolve().parent.parent
    pdf_path = base.parent / "Student_Timetables Version Ramazan.pdf"
    index_path = base / "api" / "schedules_index.json"

    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        return 1

    print("Loading project data (course map, faculty, metadata)...")
    course_map, faculty_names, room_aliases, existing = load_project_data(base)
    print(f"  Course map: {len(course_map)} codes, Faculty: {len(faculty_names)} names")

    print(f"Parsing {pdf_path}...")
    parsed = parse_pdf(str(pdf_path), course_map, faculty_names, room_aliases)
    total = sum(len(d["weekly_schedule"]) for d in parsed.values())
    print(f"Parsed {len(parsed)} students, {total} class sessions")

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
