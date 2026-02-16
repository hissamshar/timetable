from fastapi import FastAPI, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import shutil
import os
import json
from scheduler import ClassSession, ExamSession, StudentSchedule
import datetime
from ics import Calendar, Event

app = FastAPI(title="Easy Timetable API")


# CORS setup
# We use a mix of fixed origins and a fallback to handle multiple Vercel deployment URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://easytimetable.vercel.app",
    ],
    allow_origin_regex="https://timetable-.*-hissamshars-projects\.vercel\.app", # For vercel branch previews
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
OFFICIAL_PDF_DIR = os.path.join(BASE_DIR, "official_pdfs")
TEMP_DIR = os.path.join(BASE_DIR, "temp_uploads")
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
    """Returns all initial data needed by the frontend in one request."""
    try:

        # 2. Check official files
        timetable = os.path.join(OFFICIAL_PDF_DIR, "timetable.pdf")
        datesheet = os.path.join(OFFICIAL_PDF_DIR, "datesheet.pdf")
        
        # Load index to get exam type
        idx = get_index()
        
        official = {
            "timetable": {"exists": os.path.exists(timetable)},
            "datesheet": {"exists": os.path.exists(datesheet)},
            "exam_type": idx.get("exam_type", "Examination Schedule"),
            "total_students": len(idx.get("schedules", {}))
        }

        # 3. Load faculty
        faculty = []
        if os.path.exists(FACULTY_DATA_FILE):
            with open(FACULTY_DATA_FILE, "r") as f:
                faculty = json.load(f)

        # 4. Load metadata
        metadata = {"teachers": [], "venues": [], "room_aliases": {}}
        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, "r") as f:
                metadata = json.load(f)

        # 5. Load academic plan
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
        import traceback
        traceback.print_exc()
        # Fallback to empty data instead of crashing the whole request
        return {
            "official": {"timetable": {"exists": False}, "datesheet": {"exists": False}},
            "faculty": [],
            "metadata": {"teachers": [], "venues": [], "room_aliases": {}},
            "academic_plan": [],
            "error": str(e)
        }

@app.get("/api/check-official")
async def check_official_files():
    timetable = os.path.join(OFFICIAL_PDF_DIR, "timetable.pdf")
    datesheet = os.path.join(OFFICIAL_PDF_DIR, "datesheet.pdf")
    
    return {
        "timetable": {
            "exists": os.path.exists(timetable),
            "size": os.path.getsize(timetable) if os.path.exists(timetable) else 0,
            "modified": os.path.getmtime(timetable) if os.path.exists(timetable) else 0
        },
        "datesheet": {
            "exists": os.path.exists(datesheet),
            "size": os.path.getsize(datesheet) if os.path.exists(datesheet) else 0,
            "modified": os.path.getmtime(datesheet) if os.path.exists(datesheet) else 0
        }
    }

@app.post("/api/parse", response_model=StudentSchedule)
async def parse_schedule(roll_number: str = Form(...)):
    try:
        idx = get_index()
        roll_number = roll_number.strip().upper()
        
        if roll_number not in idx.get("schedules", {}):
            raise HTTPException(status_code=404, detail=f"Roll number {roll_number} not found in the official records.")
            
        data = idx["schedules"][roll_number]
        
        return StudentSchedule(
            roll_number=roll_number,
            weekly_schedule=[ClassSession(**c) for c in data["weekly_schedule"]],
            exam_schedule=[ExamSession(**e) for e in data["exam_schedule"]],
            exam_type=idx.get("exam_type", "Examination Schedule")
        )
        
    except HTTPException: raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/faculty")
async def get_faculty():
    try:
        if not os.path.exists(FACULTY_DATA_FILE): return []
        with open(FACULTY_DATA_FILE, "r") as f: return json.load(f)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/metadata")
async def get_metadata():
    try:
        if not os.path.exists(METADATA_FILE): return {"teachers": [], "venues": [], "room_aliases": {}}
        with open(METADATA_FILE, "r") as f: return json.load(f)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/academic-plan")
async def get_academic_plan():
    try:
        if not os.path.exists(ACADEMIC_PLAN_FILE): return []
        with open(ACADEMIC_PLAN_FILE, "r") as f: return json.load(f)
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download-ics")
async def download_ics(schedule: StudentSchedule):
    try:
        c = Calendar()
        
        # Add Exams (Single events)
        for exam in schedule.exam_schedule:
            e = Event()
            e.name = f"EXAM: {exam.subject}"
            try:
                # Parse date and time
                # exam.date format expected: "Mon,23,Feb,26"
                clean_date = exam.date.replace(" ", "")
                dt_date = datetime.datetime.strptime(clean_date, "%a,%d,%b,%y").date()
                start_dt = datetime.datetime.combine(dt_date, datetime.datetime.strptime(exam.start_time, "%H:%M").time())
                end_dt = datetime.datetime.combine(dt_date, datetime.datetime.strptime(exam.end_time, "%H:%M").time())
                
                e.begin = start_dt
                e.end = end_dt
                e.description = "Exam"
                c.events.add(e)
            except Exception as err:
                print(f"Skipping exam ics gen: {err}")

        # Add Classes (Recurring for Semester)
        semester_start = datetime.date(2026, 2, 2)
        day_map = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
        
        for cls in schedule.weekly_schedule:
            day_num = day_map.get(cls.day)
            if day_num is None: continue
            
            # Generate 16 weeks
            for week in range(16):
                # Calculate date
                days_ahead = day_num - semester_start.weekday()
                if days_ahead < 0: days_ahead += 7
                
                week_offset = week * 7
                current_date = semester_start + datetime.timedelta(days=days_ahead + week_offset)
                
                start_dt = datetime.datetime.combine(current_date, datetime.datetime.strptime(cls.start_time, "%H:%M").time())
                end_dt = datetime.datetime.combine(current_date, datetime.datetime.strptime(cls.end_time, "%H:%M").time())
                
                e = Event()
                e.name = cls.subject
                e.begin = start_dt
                e.end = end_dt
                e.location = cls.room
                e.description = f"Teacher: {cls.teacher}"
                try:
                    c.events.add(e)
                except Exception as err:
                     print(f"Skipping class ics gen: {err}")

        return Response(content=str(c), media_type="text/calendar", headers={"Content-Disposition": f"attachment; filename=schedule_{schedule.roll_number}.ics"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Easy Timetable API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
