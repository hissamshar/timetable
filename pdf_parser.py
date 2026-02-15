import pdfplumber
import re
import os
import json
from typing import List, Dict, Optional
from scheduler import ClassSession, ExamSession, StudentSchedule
import datetime

class PDFParser:
    def __init__(self, timetable_path: str, datesheet_path: Optional[str] = None):
        self.timetable_path = timetable_path
        self.datesheet_path = datesheet_path
        
        # Load metadata if available
        self.room_aliases = {}
        metadata_path = os.path.join(os.path.dirname(__file__), "metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    meta = json.load(f)
                    self.room_aliases = meta.get("room_aliases", {})
            except:
                pass

    def parse(self, roll_number: str) -> StudentSchedule:
        # --- NEW: Detect Exam Type ---
        exam_type = None
        if self.datesheet_path:
            exam_type = self._detect_exam_type(self.datesheet_path)

        # --- NEW: Check Static Index First ---
        index_path = os.path.join(os.path.dirname(__file__), "schedules_index.json")
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r') as f:
                    index_data = json.load(f)
                    if roll_number in index_data.get("schedules", {}):
                        cached = index_data["schedules"][roll_number]
                        print(f"DEBUG: Found {roll_number} in static index.")
                        
                        # Partial reconstruction of ClassSession objects
                        classes = [ClassSession(**c) for c in cached["weekly_schedule"]]
                        subjects = {c.subject.split(' - ')[0] for c in classes}
                        
                        # Still need to parse exams (usually smaller, or keep separate)
                        exams = []
                        if self.datesheet_path:
                            exams = self._extract_exam_schedule(subjects)
                            
                        return StudentSchedule(
                            roll_number=roll_number,
                            weekly_schedule=classes,
                            exam_schedule=exams,
                            exam_type=exam_type
                        )
            except Exception as e:
                print(f"DEBUG: Index read failed: {e}")

        # 1. Find the student's weekly schedule from the Timetable PDF
        classes, matching_subjects = self._extract_weekly_schedule(roll_number)
        
        # 2. Find the exam schedule (only if datesheet provided)
        exams = []
        if self.datesheet_path:
            exams = self._extract_exam_schedule(matching_subjects)

        return StudentSchedule(
            roll_number=roll_number,
            weekly_schedule=classes,
            exam_schedule=exams,
            exam_type=exam_type
        )

    def _detect_exam_type(self, path: str) -> str:
        """Detects if it's Sessional 1, 2, or Final from the PDF content."""
        try:
            with pdfplumber.open(path) as pdf:
                # Just check the first page text for keywords
                first_page_text = pdf.pages[0].extract_text()
                if not first_page_text:
                    # Fallback to filename if text extraction fails (e.g. image-based)
                    first_page_text = os.path.basename(path).lower()
                
                text = first_page_text.lower()
                if "sessional 1" in text or "sessional i" in text or "1st sessional" in text:
                    return "Sessional I"
                if "sessional 2" in text or "sessional ii" in text or "2nd sessional" in text:
                    return "Sessional II"
                if "final" in text:
                    return "Final Examination"
                return "Examination Schedule"
        except Exception:
            return "Examination Schedule"

    def _extract_weekly_schedule(self, roll_number: str) -> tuple[List[ClassSession], set]:
        classes = []
        subjects = set()
        
        with pdfplumber.open(self.timetable_path) as pdf:
            target_page = None
            
            # --- OPTIMIZATION (Targeted Search) ---
            # Instead of heavy table extraction on every page, 
            # we do a very fast text scan to find the exact page index.
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() # Still somewhat heavy, but better than find_tables
                if text and f"Timetable for {roll_number}" in text:
                    target_page = page
                    print(f"DEBUG: Found roll number on page {i+1}. Skipping other pages.")
                    break
            
            if not target_page:
                print(f"Roll number {roll_number} not found in timetable.")
                return [], set()

            # Extract tables and refine search
            # This is complex if multiple tables exist. 
            # Simplified approach: Look for the text position of the header, 
            # and find the table closest to it? 
            # Or assume the text extraction structure implies order.
            
            # Let's try to extract tables and see if we can correlate them to headers.
            # pdfplumber extracts tables in order. 
            # We can also extract text with layout to see "Timetable for X" y-position.
            
            # Robust Strategy: 
            # 1. Extract words/lines to find Y-coord of "Timetable for {roll_number}".
            # 2. Find the table whose top Y is nearest to that header's bottom Y.
            
            words = target_page.extract_words()
            header_y = 0
            # Construct lines to find the full header phrase
            search_phrase = f"Timetable for {roll_number}"
            # This is a bit tricky with raw words, let's use text search if simple
            # But we need coordinates.
            
            # Let's assume for now there's typically 1 or 2 per page and they are distinct.
            # If we used the text search before, we know it's there.
            
            tables = target_page.find_tables() # objects with bbox
            
            # Find header bbox
            # Simple iteration: find words that match
            # This might be brittle. Let's try a different approach:
            # The structure seen in inspection:
            # "Timetable for 20P-0087|BCS|B"
            # <Table>
            # "Timetable for 20P-0097|BCS|A"
            # <Table>
            
            # We will iterate through all tables on the page.
            # For each table, we check the text immediately *above* it.
            
            tables_obj = target_page.find_tables()
            correct_table = None
            
            for table in tables_obj:
                # bounding box: (x0, top, x1, bottom)
                # Check text above the table (e.g., previous 50 pts)
                bbox = (table.bbox[0], max(0, table.bbox[1] - 50), table.bbox[2], table.bbox[1])
                text_above = target_page.crop(bbox).extract_text()
                if text_above and f"{roll_number}" in text_above:
                    correct_table = table
                    break
            
            if correct_table:
                # content = correct_table.extract()
                # extract() gives list of lists
                # But we might need text inside to be parsed better.
                # using page.extract_tables() returns data directly
                
                # We need to map `correct_table` (which is a Table object) to the extracted data
                # Or just use correct_table.extract()
                data = correct_table.extract()
                
                # Parse the table data
                # Headers: ['', '8:00-9:30', '9:30-11:00', ...]
                headers = data[0]
                # Weekdays in column 0
                
                time_slots = []
                for h in headers[1:]:
                    if h:
                        # Clean newlines from time slots ???
                        # "8:00-9:30"
                        time_slots.append(h.replace('\n', ''))
                
                for row in data[1:]:
                    day = row[0]
                    if not day: continue
                    day = day.strip()
                    
                    for i, cell in enumerate(row[1:]):
                        if cell:
                            # Cell examples:
                            # "MG4011,BCS-8B: Entrepreneurship\nRabia Zia (Room 11)"
                            # "CL2006,BCS-6C: Operating\nSystems - Lab\nIqra Rehman (Khyber)"
                            # "CS2006,BSE-4B: Operating Systems\nFazl-e-Basit (Room 10)"
                            
                            lines = cell.split('\n')
                            
                            # --- Extract subject (first line with code pattern) ---
                            # Find the subject code from lines[0]
                            first_line = lines[0]
                            code_match = re.match(r'^([A-Z]{2}\d{4})', first_line)
                            if not code_match:
                                continue  # Not a valid class cell
                            
                            code = code_match.group(1)
                            
                            # Extract subject name after the colon
                            # The colon and name may span multiple lines
                            full_text = ' '.join(lines)
                            subject_name_match = re.search(r':\s*(.+?)(?:\s+[A-Z][a-z]+ )', full_text)
                            # Simpler: just take everything after first colon up to the teacher line
                            colon_idx = first_line.find(':')
                            if colon_idx != -1:
                                subject_name = first_line[colon_idx + 1:].strip()
                                # If subject text is truncated (ends with ...), keep as is
                                # If subject wraps to next line(s), concatenate until we hit
                                # a line containing parentheses (which is the teacher/room line)
                                for extra_line in lines[1:]:
                                    if re.search(r'\(.*?\)', extra_line):
                                        break  # This line has room info, stop concatenating
                                    subject_name += ' ' + extra_line.strip()
                            else:
                                subject_name = ""
                            
                            # Clean up truncation artifacts
                            subject_name = subject_name.rstrip('.').strip()
                            
                            full_subject = f"{code} - {subject_name}"
                            subjects.add(code)
                            
                            # --- TIME SLOT ---
                            ts = time_slots[i]
                            
                            # --- Extract room (last parenthetical in entire cell) ---
                            all_paren_matches = re.findall(r'\(([^)]+)\)', cell)
                            if all_paren_matches:
                                room = all_paren_matches[-1].strip()
                                # Clean up common room labels or use aliases
                                room_lower = room.lower()
                                if room_lower in self.room_aliases:
                                    room = self.room_aliases[room_lower]
                                elif room_lower.startswith("room "):
                                    # Fallback for just the number
                                    num = room_lower.replace("room", "").strip()
                                    if num in self.room_aliases:
                                        room = self.room_aliases[num]
                            else:
                                room = "Unknown"
                            
                            # --- Extract teacher (line containing the room parens) ---
                            teacher = "Unknown"
                            for line in reversed(lines):
                                if re.search(r'\(.*?\)', line):
                                    # Remove all parenthetical expressions to get teacher name
                                    # This handles cases like "Rabia Zia (Room 11)"
                                    teacher = re.sub(r'\([^)]*\)', '', line).strip()
                                    # Clean trailing/leading punctuation or whitespace
                                    teacher = teacher.strip(' ,;-–')
                                    break
                            
                            # Split start/end
                            start, end = ts.split('-')
                            
                            classes.append(ClassSession(
                                day=day,
                                start_time=start,
                                end_time=end,
                                subject=full_subject,
                                room=room,
                                teacher=teacher
                            ))

        # --- SORTING ---
        day_order = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        
        def get_time_val(time_str):
            try:
                # University classes: 8:00 AM to 5:30 PM
                # Times like 1:00, 2:00, 3:30, 5:00 are PM (add 12)
                # Times like 8:00, 9:30, 11:00 are AM
                h, m = map(int, time_str.split(':'))
                if h < 8:
                    h += 12
                return h * 60 + m
            except:
                return 0

        classes.sort(key=lambda x: (day_order.get(x.day, 99), get_time_val(x.start_time)))

        return classes, subjects

    def _extract_exam_schedule(self, target_subjects: set) -> List[ExamSession]:
        exams = []
        current_date_str = ""
        
        with pdfplumber.open(self.datesheet_path) as pdf:
            for page in pdf.pages:
                # We need to associate dates with tables.
                # The inspection showed: "Sat,21,Feb,26" then a table.
                # "22,Feb,26" (maybe?) then table.
                
                # Strategy: Extract text to find dates, and find associated rows.
                # Or extract tables and look at text above them, similar to before.
                
                tables_obj = page.find_tables()
                
                for table in tables_obj:
                    # Look for date above the table
                    bbox = (0, max(0, table.bbox[1] - 80), page.width, table.bbox[1])
                    text_above = page.crop(bbox).extract_text()
                    
                    # Try to parse date from text_above
                    # Pattern: "Sat,21,Feb,26" or similar
                    # Regex for date
                    date_match = re.search(r'([A-Za-z]+, \d{1,2}, [A-Za-z]+, \d{2})', text_above)
                    # The sample showed: "Sat,21,Feb,26" -> spaces might be newlines or tight
                    if not date_match:
                         date_match = re.search(r'(\w+,\s*\d{1,2},\s*\w+,\s*\d{2})', text_above)
                    
                    if date_match:
                        raw_date = date_match.group(1)
                        # Format: "Sat,21,Feb,26" -> "Sat, 21 Feb 2026"
                        parts = raw_date.split(',')
                        if len(parts) == 4:
                            current_date_str = f"{parts[0]}, {parts[1]} {parts[2]} 20{parts[3]}"
                        else:
                            current_date_str = raw_date
                    
                    # If we didn't find a new date, we keep the old one (if valid)
                    # But multiple tables might be under one date? 
                    # Assuming Date -> Table 
                    
                    data = table.extract()
                    if not data: continue
                    
                    # Row 0 is usually time slots: "8:30-9:30", etc.
                    # Warning: The inspection showed Row 0 as counts sometimes?
                    # "Table 0: [['8:30-9:30', '10:00-11:00'...], ['348', '240'...]]"
                    # So Row 0 is Headers.
                    
                    headers = data[0]
                    # Check if headers look like times
                    if not any(":" in h for h in headers if h):
                        # Might be a continuation or data row. Skip for now to be safe
                        continue
                        
                    # Rows contain cells with subject info
                    # "MT2005 - Probability and Statistics|BAI-4..."
                    
                    for row_idx, row in enumerate(data[1:], start=1):
                        for col_idx, cell in enumerate(row):
                            if cell and any(s in cell for s in target_subjects):
                                # Found a match!
                                # Confirm it is the subject code (e.g., "CS4075 -")
                                # Because "CS4075" is in "CS4075 - Cloud..."
                                
                                # Check which subject matched
                                matched_subject = None
                                for s in target_subjects:
                                    if s in cell:
                                        matched_subject = s
                                        break
                                
                                if matched_subject:
                                    # Extract Time
                                    time_slot = headers[col_idx]
                                    start, end = time_slot.split('-')
                                    
                                    # Clean date? "Sat,21,Feb,26" -> YYYY-MM-DD
                                    # parser can handle specific formats, but lets try dateutil
                                    
                                    raw_cell = cell.replace('\n', ' ')
                                    
                                    # 1. Extract Course (Find the pattern XX#### - Name)
                                    # Pattern: 2 Letters, 4 Digits, Dash, then text
                                    subject_match = re.search(r'([A-Z]{2}\d{4}\s*-\s*[^|]+)', raw_cell)
                                    subject_part = ""
                                    if subject_match:
                                        subject_part = subject_match.group(1).split('|')[0].strip()
                                    else:
                                        # Fallback to before pipe
                                        subject_part = raw_cell.split('|')[0].strip()
                                    
                                    # 2. Extract Teachers
                                    # Logic: Highlighting everything that ISN'T the subject part, section, or strength
                                    # Let's remove strength and section first
                                    clean_for_teachers = re.sub(r'\|[^ ]+', '', raw_cell) # Remove section like |MCS-4
                                    clean_for_teachers = re.sub(r'\(St:\s*\d+\)', '', clean_for_teachers) # Remove (St: 1)
                                    
                                    # Remove the subject part from the cell to get teachers
                                    if subject_part:
                                        clean_for_teachers = clean_for_teachers.replace(subject_part, '')
                                    
                                    # Cleanup: remove remaining punctuation/junk
                                    teacher_part = clean_for_teachers.replace('|', ' ').strip()
                                    teacher_part = re.sub(r'\s+', ' ', teacher_part).strip(', ').strip()
                                    
                                    # Handle the case where the user example has teacher both at start and end
                                    # If teacher_part has a comma at the end, clean it
                                    teacher_part = teacher_part.strip(',').strip()
                                    
                                    exams.append(ExamSession(
                                        subject=subject_part,
                                        date=current_date_str,
                                        start_time=start,
                                        end_time=end,
                                        room=teacher_part # Storing teacher in room
                                    ))
        
        return exams

if __name__ == "__main__":
    # Test
    parser = PDFParser("Student_Timetables V#3 Spring-2026.pdf", "Tentative Datesheet Sessional 1 Spring-2026.pdf")
    schedule = parser.parse("24P-0529") # User provided roll number
    if (len(schedule.weekly_schedule) == 0):
        # Fallback/Debug: Try one that we know exists from inspection
        print("Target roll number not found, trying 20P-0087 for debug...")
        schedule = parser.parse("20P-0087")
        
    print(schedule.model_dump_json(indent=2))
