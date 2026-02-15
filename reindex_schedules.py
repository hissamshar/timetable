import pdfplumber
import json
import os
import re
import hashlib
from typing import Dict, Any
from pdf_parser import PDFParser
from scheduler import ClassSession, StudentSchedule

def calculate_pdf_hash(pdf_path: str) -> str:
    hasher = hashlib.md5()
    with open(pdf_path, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def reindex_timetable(timetable_path: str, output_path: str = "schedules_index.json"):
    print(f"Starting re-indexing of {timetable_path}...")
    
    # We use a specialized parsing loop for indexing
    index_data = {
        "pdf_hash": calculate_pdf_hash(timetable_path),
        "schedules": {}
    }
    
    # Re-use the existing PDFParser logic but wrapped for bulk extraction
    # We'll create a lightweight version here that processes page by page
    
    with pdfplumber.open(timetable_path) as pdf:
        total_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            print(f"Processing page {i+1}/{total_pages}...")
            text = page.extract_text()
            if not text:
                continue
            
            # Find all "Timetable for <RollNo>" occurrences on this page
            # Pattern: "Timetable for 20P-0087|BCS|B"
            headers = re.findall(r'Timetable for ([\w-]+)\|', text)
            
            if not headers:
                continue
            
            # For each roll number found, extract their specific table
            # We reuse the logic from PDFParser._extract_weekly_schedule but targeted
            tables_obj = page.find_tables()
            
            for roll_no in headers:
                # Find the table associated with this roll_no
                correct_table = None
                for table in tables_obj:
                    # bounding box: (x0, top, x1, bottom)
                    # Check text above the table
                    bbox = (table.bbox[0], max(0, table.bbox[1] - 50), table.bbox[2], table.bbox[1])
                    text_above = page.crop(bbox).extract_text()
                    if text_above and roll_no in text_above:
                        correct_table = table
                        break
                
                if correct_table:
                    # Extract the schedule (re-using the logic from PDFParser)
                    # For simplicity in this script, we'll instantiate a PDFParser 
                    # but we need to avoid it re-opening the PDF. 
                    # Let's just implement the table-to-schedule conversion.
                    
                    data = correct_table.extract()
                    schedule = parse_table_data_to_sessions(data)
                    
                    index_data["schedules"][roll_no] = {
                        "page_index": i,
                        "weekly_schedule": [s.model_dump() for s in schedule]
                    }

    with open(output_path, 'w') as f:
        json.dump(index_data, f, indent=2)
    
    print(f"Re-indexing complete. Indexed {len(index_data['schedules'])} roll numbers.")

def parse_table_data_to_sessions(data):
    # This is a copy of the logic in PDFParser to avoid circular dependencies 
    # and keep the indexer efficient.
    classes = []
    headers = data[0]
    time_slots = []
    for h in headers[1:]:
        if h:
            time_slots.append(h.replace('\n', ''))
    
    for row in data[1:]:
        day = row[0]
        if not day: continue
        day = day.strip()
        
        for i, cell in enumerate(row[1:]):
            if cell:
                lines = cell.split('\n')
                first_line = lines[0]
                code_match = re.match(r'^([A-Z]{2}\d{4})', first_line)
                if not code_match: continue
                
                code = code_match.group(1)
                colon_idx = first_line.find(':')
                if colon_idx != -1:
                    subject_name = first_line[colon_idx + 1:].strip()
                    for extra_line in lines[1:]:
                        if re.search(r'\(.*?\)', extra_line): break
                        subject_name += ' ' + extra_line.strip()
                else:
                    subject_name = ""
                
                subject_name = subject_name.rstrip('.').strip()
                full_subject = f"{code} - {subject_name}"
                ts = time_slots[i]
                
                all_paren_matches = re.findall(r'\(([^)]+)\)', cell)
                room = all_paren_matches[-1].strip() if all_paren_matches else "Unknown"
                
                teacher = "Unknown"
                for line in reversed(lines):
                    if re.search(r'\(.*?\)', line):
                        teacher = re.sub(r'\([^)]*\)', '', line).strip().strip(' ,;-–')
                        break
                
                start, end = ts.split('-')
                classes.append(ClassSession(
                    day=day, start_time=start, end_time=end,
                    subject=full_subject, room=room, teacher=teacher
                ))
    
    # Sorting
    day_order = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
    def get_time_val(time_str):
        h, m = map(int, time_str.split(':'))
        if h < 8: h += 12
        return h * 60 + m
    
    classes.sort(key=lambda x: (day_order.get(x.day, 99), get_time_val(x.start_time)))
    return classes

if __name__ == "__main__":
    reindex_timetable("Student_Timetables V#3 Spring-2026.pdf")
