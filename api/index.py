from fastapi import FastAPI, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import os
import sys
import json
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from ics import Calendar, Event

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

app = FastAPI(title="Easy Timetable API")

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

@app.post("/api/parse", response_model=StudentSchedule)
async def parse_schedule(roll_number: str = Form(...)):
    try:
        idx = get_index()
        roll_number = roll_number.strip().upper()
        
        if roll_number not in idx.get("schedules", {}):
            raise HTTPException(status_code=404, detail=f"Roll number {roll_number} not found.")
            
        data = idx["schedules"][roll_number]
        
        return StudentSchedule(
            roll_number=roll_number,
            weekly_schedule=[ClassSession(**c) for c in data["weekly_schedule"]],
            exam_schedule=[ExamSession(**e) for e in data["exam_schedule"]],
            exam_type=idx.get("exam_type", "Examination Schedule")
        )
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/download-ics")
async def download_ics(schedule: StudentSchedule):
    try:
        c = Calendar()
        
        for exam in schedule.exam_schedule:
            e = Event()
            e.name = f"EXAM: {exam.subject}"
            try:
                clean_date = exam.date.replace(" ", "")
                dt_date = datetime.strptime(clean_date, "%a,%d,%b,%y").date()
                start_dt = datetime.combine(dt_date, datetime.strptime(exam.start_time, "%H:%M").time())
                end_dt = datetime.combine(dt_date, datetime.strptime(exam.end_time, "%H:%M").time())
                e.begin = start_dt
                e.end = end_dt
                c.events.add(e)
            except: pass

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
                    
                    e = Event()
                    e.name = cls.subject
                    e.begin = start_dt
                    e.end = end_dt
                    e.location = cls.room
                    c.events.add(e)
                except: pass

        return Response(content=str(c), media_type="text/calendar", headers={"Content-Disposition": f"attachment; filename=schedule_{schedule.roll_number}.ics"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
@app.get("/api")
def read_root():
    return {"message": "Easy Timetable API is running"}
