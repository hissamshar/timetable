from fastapi import FastAPI, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import os
import sys
import json
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
# from ics import Calendar, Event

# Self-contained models to avoid import issues on Vercel
class ClassSession(BaseModel):
    day: str
    start_time: str
    end_time: str
    subject: str
    room: str
    teacher: str

class ExamSession(BaseModel):
    subject: str
    date: str
    start_time: str
    end_time: str
    room: Optional[str] = None

class StudentSchedule(BaseModel):
    roll_number: str
    weekly_schedule: List[ClassSession]
    exam_schedule: List[ExamSession]
    exam_type: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.now)

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, "schedules_index.json")
FACULTY_DATA_FILE = os.path.join(BASE_DIR, "faculty_data.json")
ACADEMIC_PLAN_FILE = os.path.join(BASE_DIR, "academic_plan.json")
METADATA_FILE = os.path.join(BASE_DIR, "metadata.json")

# Global index cache
_index_cache = None

def get_index():
    global _index_cache
    if _index_cache is None:
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, "r") as f:
                    _index_cache = json.load(f)
            except Exception as e:
                print(f"Error loading index: {e}")
                _index_cache = {"exam_type": "Examination Schedule", "schedules": {}}
        else:
            _index_cache = {"exam_type": "Examination Schedule", "schedules": {}}
    return _index_cache

# Handle /api and also /api/
@app.get("/api")
@app.get("/api/")
def health_check():
    return {"status": "ok", "message": "Easy Timetable API is running via Vercel api/index.py"}

# Handle /api/bootstrap and /bootstrap
@app.get("/bootstrap")
@app.get("/api/bootstrap")
async def bootstrap():
    try:
        idx = get_index()
        
        official = {
            "timetable": {"exists": True},
            "datesheet": {"exists": True},
            "exam_type": idx.get("exam_type", "Examination Schedule"),
            "total_students": len(idx.get("schedules", {}))
        }

        faculty = []
        if os.path.exists(FACULTY_DATA_FILE):
            with open(FACULTY_DATA_FILE, "r") as f:
                faculty = json.load(f)

        metadata = {"teachers": [], "venues": [], "room_aliases": {}}
        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, "r") as f:
                metadata = json.load(f)

        academic_plan = []
        if os.path.exists(ACADEMIC_PLAN_FILE):
            with open(ACADEMIC_PLAN_FILE, "r") as f:
                academic_plan = json.load(f)

        return {
            "official": official,
            "faculty": faculty,
            "metadata": metadata,
            "academic_plan": academic_plan
        }
    except Exception as e:
        return {
            "official": {"timetable": {"exists": False}, "datesheet": {"exists": False}},
            "faculty": [],
            "metadata": {"teachers": [], "venues": [], "room_aliases": {}},
            "academic_plan": [],
            "error": str(e)
        }

# Handle /api/parse and /parse
@app.post("/parse")
@app.post("/api/parse")
async def parse_schedule(roll_number: str = Form(...)):
    try:
        idx = get_index()
        roll_number = roll_number.strip().upper()
        
        if roll_number not in idx.get("schedules", {}):
            raise HTTPException(status_code=404, detail=f"Roll number {roll_number} not found.")
            
        data = idx["schedules"][roll_number]
        
        # Process weekly schedule to fix Lab durations and incorrect names
        weekly_schedule = []
        for c in data["weekly_schedule"]:
            # Fix Course Names
            if "Probability and Stat" in c['subject'] and "Statistics" not in c['subject']:
                c['subject'] = c['subject'].replace("Probability and Stat", "Probability and Statistics")
            
            # Additional naming fixes
            name_fixes = {
                "SS1015 - Pakistan Studies|2Hr": "SS1015 - Pakistan Studies",
                "AL2002 - Artificial Intellige": "AL2002 - Artificial Intelligence - Lab",
                "AI2002 - Artificial Intellige": "AI2002 - Artificial Intelligence",
                "MT1008 - Multivariable Calcul": "MT1008 - Multivariable Calculus",
                "CL2006 - Operating Systems -": "CL2006 - Operating Systems - Lab",
                "CL2005 - Database Systems - L": "CL2005 - Database Systems - Lab"
            }
            for old_name, new_name in name_fixes.items():
                if c['subject'] == old_name:
                    c['subject'] = new_name
                elif c['subject'].startswith(old_name) and new_name not in c['subject']:
                    c['subject'] = new_name

            # Fix Teacher Names
            if c.get('teacher') == "Hafeez Ur Rehman":
                c['teacher'] = "Dr. Hafeez-ur Rehman"
            elif c.get('teacher') == "Askar Ali":
                c['teacher'] = "Dr. Askar Ali"

            # Check if it's a lab
            # - Room contains "Lab"
            # - Subject contains "Lab"
            # - Subject code starts with "CL" (e.g. CL2006)
            # - Subject ends with "- Lab"
            subject_upper = c.get('subject', '').upper()
            room_upper = c.get('room', '').upper()
            
            is_lab = (
                'LAB' in room_upper or 
                'LAB' in subject_upper or 
                subject_upper.startswith('CL') or 
                subject_upper.endswith('- LAB')
            )
            
            if is_lab:
                try:
                    # Parse start time
                    start_dt = datetime.strptime(c['start_time'], "%H:%M")
                    # Set end time to start + 3 hours
                    end_dt = start_dt + timedelta(hours=3)
                    # Update end time string
                    c = c.copy() # Don't mutate original if cached
                    c['end_time'] = end_dt.strftime("%-H:%M") # %-H for no leading zero if possible, or %H
                    if ':' not in c['end_time']: # Fallback for some systems
                         c['end_time'] = end_dt.strftime("%H:%M")
                except Exception as e:
                    print(f"Error fixing lab time: {e}")
            
            weekly_schedule.append(ClassSession(**c))

        return StudentSchedule(
            roll_number=roll_number,
            weekly_schedule=weekly_schedule,
            exam_schedule=[ExamSession(**e) for e in data["exam_schedule"]],
            exam_type=idx.get("exam_type", "Examination Schedule")
        )
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/api/download-ics")
@app.post("/download-ics")
async def download_ics(schedule: StudentSchedule):
    try:
        def format_dt(dt):
            return dt.strftime("%Y%m%dT%H%M%S")

        ics_content = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Easy Timetable//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH"
        ]

        # Exams
        for exam in schedule.exam_schedule:
            try:
                clean_date = exam.date.replace(" ", "")
                dt_date = datetime.strptime(clean_date, "%a,%d,%b,%y").date()
                start_dt = datetime.combine(dt_date, datetime.strptime(exam.start_time, "%H:%M").time())
                end_dt = datetime.combine(dt_date, datetime.strptime(exam.end_time, "%H:%M").time())
                
                ics_content.extend([
                    "BEGIN:VEVENT",
                    f"SUMMARY:EXAM: {exam.subject}",
                    f"DTSTART:{format_dt(start_dt)}",
                    f"DTEND:{format_dt(end_dt)}",
                    f"DESCRIPTION:Room: {exam.room or 'TBD'}",
                    f"LOCATION:{exam.room or 'TBD'}",
                    "STATUS:CONFIRMED",
                    "END:VEVENT"
                ])
            except: pass

        # Classes
        semester_start = date(2026, 2, 2)
        day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        
        for cls in schedule.weekly_schedule:
            day_num = day_map.get(cls.day)
            if day_num is None: continue
            
            for week in range(16):
                days_ahead = day_num - semester_start.weekday()
                if days_ahead < 0: days_ahead += 7
                current_date = semester_start + timedelta(days=days_ahead + (week * 7))
                
                try:
                    start_dt = datetime.combine(current_date, datetime.strptime(cls.start_time, "%H:%M").time())
                    end_dt = datetime.combine(current_date, datetime.strptime(cls.end_time, "%H:%M").time())
                    
                    ics_content.extend([
                        "BEGIN:VEVENT",
                        f"SUMMARY:{cls.subject}",
                        f"DTSTART:{format_dt(start_dt)}",
                        f"DTEND:{format_dt(end_dt)}",
                        f"DESCRIPTION:Teacher: {cls.teacher}",
                        f"LOCATION:{cls.room}",
                        "STATUS:CONFIRMED",
                        "END:VEVENT"
                    ])
                except: pass

        ics_content.append("END:VCALENDAR")
        return Response(content="\r\n".join(ics_content), media_type="text/calendar", headers={"Content-Disposition": f"attachment; filename=schedule_{schedule.roll_number}.ics"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
