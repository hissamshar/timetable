import pdfplumber
import json
import os
import re
from typing import List, Dict, Set, Any
from pdf_parser import PDFParser
from scheduler import ClassSession, ExamSession, StudentSchedule

def reindex_all_optimized(timetable_path: str, datesheet_path: str, output_path: str = "schedules_index.json"):
    print(f"--- Starting OPTIMIZED Bulk Re-indexing ---")
    
    # 1. Initialize Parser and Pre-parse Exams
    parser = PDFParser(timetable_path, datesheet_path)
    exam_type = parser._detect_exam_type(datesheet_path)
    
    print("Pre-parsing all exams...")
    # We need a list of all exams to filter from
    # Actually, we can just extract all rows from the datesheet once
    all_exams_raw = []
    with pdfplumber.open(datesheet_path) as pdf:
        current_date = ""
        for page in pdf.pages:
            tables = page.find_tables()
            for table in tables:
                # Find date above
                bbox = (0, max(0, table.bbox[1] - 80), page.width, table.bbox[1])
                text_above = page.crop(bbox).extract_text()
                date_match = re.search(r'(\w+,\s*\d{1,2},\s*\w+,\s*\d{2})', text_above or "")
                if date_match:
                    raw_date = date_match.group(1)
                    parts = raw_date.split(',')
                    if len(parts) == 4:
                        current_date = f"{parts[0]}, {parts[1]} {parts[2]} 20{parts[3]}"
                
                data = table.extract()
                if not data or len(data) < 2: continue
                headers = data[0]
                if not any(":" in h for h in headers if h): continue
                
                for row in data[1:]:
                    for col_idx, cell in enumerate(row):
                        if cell:
                            all_exams_raw.append({
                                "cell": cell,
                                "header": headers[col_idx],
                                "date": current_date
                            })
    print(f"Extracted {len(all_exams_raw)} total exam slots.")

    # 2. Process Timetable Page by Page
    index_data = {
        "exam_type": exam_type,
        "schedules": {}
    }

    print("Processing timetable pages...")
    with pdfplumber.open(timetable_path) as pdf:
        total_pages = len(pdf.pages)
        for p_idx, page in enumerate(pdf.pages):
            print(f"Processing page {p_idx+1}/{total_pages}...")
            text = page.extract_text()
            if not text: continue
            
            # Find all roll numbers on this page
            roll_headers = re.findall(r'Timetable for ([\w-]+)\|', text)
            if not roll_headers: continue
            
            tables_obj = page.find_tables()
            for roll_no in roll_headers:
                # Find the table for this student
                correct_table = None
                for table in tables_obj:
                    bbox = (table.bbox[0], max(0, table.bbox[1] - 50), table.bbox[2], table.bbox[1])
                    text_above = page.crop(bbox).extract_text()
                    if text_above and roll_no in text_above:
                        correct_table = table
                        break
                
                if correct_table:
                    # 1. Extract Weekly Schedule
                    data = correct_table.extract()
                    # Use a helper to parse table data (logic from reindex_schedules.py)
                    weekly_schedule = parse_table_data_to_sessions(data)
                    
                    # 2. Extract Matching Exams
                    subject_codes = {s.subject.split(' - ')[0] for s in weekly_schedule}
                    matched_exams = []
                    for ex in all_exams_raw:
                        if any(code in ex["cell"] for code in subject_codes):
                            # Refine exam extraction (logic from pdf_parser.py)
                            session = extract_exam_session(ex, subject_codes)
                            if session:
                                matched_exams.append(session.model_dump())
                    
                    index_data["schedules"][roll_no] = {
                        "weekly_schedule": [s.model_dump() for s in weekly_schedule],
                        "exam_schedule": matched_exams
                    }

    # 3. Save
    with open(output_path, 'w') as f:
        json.dump(index_data, f, indent=2)
    
    print(f"--- Bulk Re-indexing Complete ---")
    print(f"Indexed {len(index_data['schedules'])} schedules to {output_path}")

def parse_table_data_to_sessions(data):
    # Same logic as before
    classes = []
    headers = data[0]
    time_slots = [h.replace('\n', '') for h in headers[1:] if h]
    
    for row in data[1:]:
        day = (row[0] or "").strip()
        if not day: continue
        
        for i, cell in enumerate(row[1:]):
            if cell:
                lines = cell.split('\n')
                first_line = lines[0]
                code_match = re.match(r'^([A-Z]{2}\d{4})', first_line)
                if not code_match: continue
                
                code = code_match.group(1)
                colon_idx = first_line.find(':')
                subject_name = first_line[colon_idx + 1:].strip() if colon_idx != -1 else ""
                for extra_line in lines[1:]:
                    if re.search(r'\(.*?\)', extra_line): break
                    subject_name += ' ' + extra_line.strip()
                
                full_subject = f"{code} - {subject_name.rstrip('.').strip()}"
                
                all_paren_matches = re.findall(r'\(([^)]+)\)', cell)
                room = all_paren_matches[-1].strip() if all_paren_matches else "Unknown"
                
                teacher = "Unknown"
                for line in reversed(lines):
                    if re.search(r'\(.*?\)', line):
                        teacher = re.sub(r'\([^)]*\)', '', line).strip(' ,;-– ')
                        break
                
                ts = time_slots[i]
                start, end = ts.split('-')
                classes.append(ClassSession(day=day, start_time=start, end_time=end, subject=full_subject, room=room, teacher=teacher))
    
    day_order = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    def get_time_val(t):
        h, m = map(int, t.split(':'))
        if h < 8: h += 12
        return h * 60 + m
    classes.sort(key=lambda x: (day_order.get(x.day, 99), get_time_val(x.start_time)))
    return classes

def extract_exam_session(ex_raw: dict, target_codes: set):
    cell = ex_raw["cell"].replace('\n', ' ')
    matched_code = None
    for code in target_codes:
        if code in cell:
            matched_code = code
            break
    if not matched_code: return None
    
    start, end = ex_raw["header"].split('-')
    subject_match = re.search(r'([A-Z]{2}\d{4}\s*-\s*[^|]+)', cell)
    subject_part = subject_match.group(1).split('|')[0].strip() if subject_match else cell.split('|')[0].strip()
    
    clean_teachers = re.sub(r'\|[^ ]+', '', cell)
    clean_teachers = re.sub(r'\(St:\s*\d+\)', '', clean_teachers)
    if subject_part: clean_teachers = clean_teachers.replace(subject_part, '')
    teacher_part = clean_teachers.replace('|', ' ').strip(', ').strip()
    
    return ExamSession(subject=subject_part, date=ex_raw["date"], start_time=start, end_time=end, room=teacher_part)

if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TIMETABLE = os.path.join(BASE_DIR, "official_pdfs", "timetable.pdf")
    DATESHEET = os.path.join(BASE_DIR, "official_pdfs", "datesheet.pdf")
    reindex_all_optimized(TIMETABLE, DATESHEET)
