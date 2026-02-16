from fastapi import FastAPI, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import os
import sys
import json
import datetime

# Vercel path safeguard
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

try:
    from scheduler import ClassSession, ExamSession, StudentSchedule
except ImportError:
    # Fallback for local dev or specific Vercel layouts
    sys.path.append(os.getcwd())
    from scheduler import ClassSession, ExamSession, StudentSchedule

from ics import Calendar, Event

app = FastAPI(title="Easy Timetable API")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
            with open(INDEX_FILE, "r") as f:
                _index_cache = json.load(f)
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
                dt_date = datetime.datetime.strptime(clean_date, "%a,%d,%b,%y").date()
                start_dt = datetime.datetime.combine(dt_date, datetime.datetime.strptime(exam.start_time, "%H:%M").time())
                end_dt = datetime.datetime.combine(dt_date, datetime.datetime.strptime(exam.end_time, "%H:%M").time())
                e.begin = start_dt
                e.end = end_dt
                c.events.add(e)
            except: pass

        semester_start = datetime.date(2026, 2, 2)
        day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        
        for cls in schedule.weekly_schedule:
            day_num = day_map.get(cls.day)
            if day_num is None: continue
            
            for week in range(16):
                days_ahead = day_num - semester_start.weekday()
                if days_ahead < 0: days_ahead += 7
                current_date = semester_start + datetime.timedelta(days=days_ahead + (week * 7))
                
                try:
                    start_dt = datetime.datetime.combine(current_date, datetime.datetime.strptime(cls.start_time, "%H:%M").time())
                    end_dt = datetime.datetime.combine(current_date, datetime.datetime.strptime(cls.end_time, "%H:%M").time())
                    
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
