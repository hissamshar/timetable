import pdfplumber
import json
import re
import os
import sys

student_pdf = "Student_Timetables V#5 Spring-2026.pdf"
exam_pdfs = [
    "../Final_Exam_DateSheet_Report.pdf",
    "../Lab Exam DateSheet_Report.pdf"
]
json_path = "api/schedules_index.json"

def clean_text(text):
    if not text: return ""
    return text.replace("\n", " ").strip()

# 1. Parse Student Timetables
def parse_student_timetables():
    schedules = {}
    with pdfplumber.open(student_pdf) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            if not text: continue
            
            # Find roll numbers (e.g. 19P-0401)
            # Timetable for 20P-0004
            roll_nos = re.findall(r'Timetable for\s+([A-Z0-9\-]+)', text, flags=re.IGNORECASE)
            tables = page.extract_tables()
            
            if len(roll_nos) != len(tables):
                print(f"Warning: page {page_num} roll_nos count {len(roll_nos)} != tables count {len(tables)}")
            
            for index, table in enumerate(tables):
                if index >= len(roll_nos): break
                roll_no = roll_nos[index].upper()
                
                schedules[roll_no] = {"weekly_schedule": [], "exam_schedule": []}
                
                header = table[0]
                times = header[1:] # e.g. ['8:00-9:30', '9:30-11:00']
                
                for row in table[1:]:
                    day = row[0]
                    if not day or day.strip() == "": continue
                    day = day.strip()
                    
                    for col_idx, cell in enumerate(row[1:]):
                        if not cell or cell.strip() == "": continue
                        
                        time_slot = times[col_idx]
                        if "-" not in time_slot: continue
                        t_start, t_end = time_slot.split("-")
                        t_start, t_end = t_start.strip(), t_end.strip()
                        
                        # cell example: CS3002,BAI-8A: Information\nSecurity\nAli Sayyed (Room 2)
                        lines = cell.split("\n")
                        subject_lines = []
                        teacher_room = ""
                        for part in lines:
                            if "(" in part and ")" in part:
                                teacher_room = part
                            elif part.strip():
                                subject_lines.append(part.strip())
                        
                        subject = " ".join(subject_lines)
                        teacher = teacher_room
                        room = ""
                        
                        m = re.search(r'\((.*?)\)', teacher_room)
                        if m:
                            room = m.group(1).strip()
                            teacher = teacher_room[:m.start()].strip()
                        
                        schedules[roll_no]["weekly_schedule"].append({
                            "day": day,
                            "start_time": t_start,
                            "end_time": t_end,
                            "subject": subject,
                            "room": room,
                            "teacher": teacher
                        })
    return schedules

# 2. Parse Exam Datesheet
def parse_exams(pdf_file):
    exams = []
    
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            tables = page.extract_tables()
            
            # Find dates (e.g. Thu,09,Apr,26)
            # They usually appear above the table. We can find them using regex.
            dates = re.findall(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*\d{1,2},\s*[A-Za-z]{3},\s*\d{2,4}', text)
            
            if not tables: continue
            
            for index, table in enumerate(tables):
                if index >= len(dates): break
                date_str = dates[index]
                
                header = table[0]
                times = [t for t in header if "-" in t]
                
                # Usually row 1 is counts (e.g. 462), skip it if no letters. exams start from row 2
                start_row = 1
                if all(re.match(r'^\d+$', c.strip()) for c in table[1] if c is not None and c.strip()):
                    start_row = 2
                
                for row_num in range(start_row, len(table)):
                    row = table[row_num]
                    # Map each column cell to the time
                    for col_idx, cell in enumerate(row):
                        if col_idx >= len(times) or not cell or not str(cell).strip(): continue
                        time_slot = times[col_idx]
                        t_start, t_end = time_slot.split("-")
                        t_start, t_end = t_start.strip(), t_end.strip()
                        
                        text_cell = str(cell)
                        # Split by courses
                        parts = re.split(r'(?=\b[A-Z]{2,3}[0-9]{3,4}\s*-)', text_cell)
                        for part in parts:
                            if not part.strip(): continue
                            part = part.strip()
                            # Parse format: CS3014 - Applied Human Computer Interaction ! 1Hr | BCS-6 (St: 115) \n Teacher
                            lines = part.split("\n")
                            course_code_match = re.search(r'^([A-Z]{2,3}[0-9]{3,4})\s*-\s*([^!]+)!\s*(.*)', lines[0])
                            
                            course_code = ""
                            subject = ""
                            teacher = ""
                            if course_code_match:
                                course_code = course_code_match.group(1).strip()
                                subject_name = course_code_match.group(2).strip()
                                subject = f"{course_code} - {subject_name}"
                            else:
                                subject = clean_text(lines[0])
                                m2 = re.search(r'^([A-Z]{2,3}[0-9]{3,4})', subject)
                                if m2: course_code = m2.group(1)
                            
                            # Teacher is usually anything after the line with '|'
                            teacher_lines = []
                            found_pipe = False
                            for line in lines:
                                if "|" in line:
                                    found_pipe = True
                                    continue
                                if found_pipe:
                                    teacher_lines.append(line.strip())
                            
                            if teacher_lines:
                                teacher = " ".join(teacher_lines)
                            
                            exams.append({
                                "date": date_str.replace(" ", ""),
                                "start_time": t_start,
                                "end_time": t_end,
                                "subject": subject,
                                "course_code": course_code,
                                "teacher": teacher,
                                "room": "" # Not specified in typical datesheet cell easily, or wait, is it? We don't need room immediately or we can leave it empty.
                            })
    return exams

def update_data():
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            data = json.load(f)
    else:
        data = {"exam_type": "Final Exam", "schedules": {}}
        
    data["exam_type"] = "Final Exam"
    old_schedules = data.get("schedules", {})
    
    print("Parsing Student Timetables...")
    new_schedules = parse_student_timetables()
    
    # Merge
    for roll, sched in new_schedules.items():
        if roll not in old_schedules:
            old_schedules[roll] = {"weekly_schedule": [], "exam_schedule": []}
        old_schedules[roll]["weekly_schedule"] = sched["weekly_schedule"]
        # Clear out exam_schedule for regeneration
        old_schedules[roll]["exam_schedule"] = []
    
    print("Parsing Exam Datesheets...")
    all_exams = []
    for pdf_file in exam_pdfs:
        print(f"Parsing {pdf_file}...")
        all_exams.extend(parse_exams(pdf_file))
    
    print(f"Assigning {len(all_exams)} exam slots to students...")
    # Assign exams to students
    matched_exams = 0
    for roll, sched in old_schedules.items():
        # Get list of course codes the student is taking
        student_courses = set()
        for w in sched.get("weekly_schedule", []):
            subj = w.get("subject", "")
            m = re.search(r'^([A-Z]{2,3}[0-9]{3,4})', subj)
            if m: student_courses.add(m.group(1))
            
        for exam in all_exams:
            if exam["course_code"] and exam["course_code"] in student_courses:
                sched["exam_schedule"].append({
                    "date": exam["date"],
                    "start_time": exam["start_time"],
                    "end_time": exam["end_time"],
                    "subject": exam["subject"],
                    "room": exam["room"],
                    "teacher": exam["teacher"]
                })
                matched_exams += 1

    data["schedules"] = old_schedules
    
    print(f"Total matched exam entries for students: {matched_exams}")

    # Write backup of the regular one if needed or just write directly 
    # since we are creating it natively.
    backup_path = "api/schedules_index_regular.json"
    print(f"Writing to {backup_path} and {json_path}")
    with open(backup_path, "w") as f:
        json.dump(data, f, indent=2)
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    update_data()
    print("Done!")
