from fastapi import FastAPI, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import os
import sys
import json
import re
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
# from ics import Calendar, Event
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Optional[Client] = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Self-contained models to avoid import issues on Vercel
class LiveUpdate(BaseModel):
    id: str
    status: str
    course_code: str
    original_day: str
    original_time: str
    new_day: Optional[str] = None
    new_time: Optional[str] = None
    new_room: Optional[str] = None
    reason: Optional[str] = None
    teacher: Optional[str] = None # Added for display
    description: Optional[str] = None # Added for display
    created_at: str

    @property
    def extracted_teacher(self):
        if not self.reason: return "Unknown"
        match = re.match(r"^\[(.*?)\]", self.reason)
        return match.group(1) if match else "Unknown"

    @property
    def cleaned_reason(self):
        if not self.reason: return ""
        return re.sub(r"^\[.*?\]\s*", "", self.reason)

class ClassSession(BaseModel):
    day: str
    start_time: str
    end_time: str
    subject: str
    room: str
    teacher: str
    live_status: Optional[str] = None # Added for live updates
    live_reason: Optional[str] = None # Added for live updates
    live_new_time: Optional[str] = None # Added for live updates
    live_new_room: Optional[str] = None # Added for live updates

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
    live_updates: List[LiveUpdate] = [] # Added for frontend alerts
    campus_events: List[LiveUpdate] = [] # New: Dedicated list for events
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
    env_keys = list(os.environ.keys())
    return {
        "status": "online",
        "supabase_configured": supabase is not None,
        "available_keys": [k for k in env_keys if "SUPABASE" in k or "GROQ" in k or "GMAIL" in k],
        "python_version": "3.12"
    }

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
        
        # Fetch Live Updates from Supabase
        live_data = []
        if supabase:
            try:
                print(f"Fetching updates from Supabase: {SUPABASE_URL}")
                res = supabase.table("live_updates").select("*").execute()
                live_data = res.data or []
                print(f"Found {len(live_data)} updates in Supabase.")
            except Exception as e:
                print(f"Supabase error: {e}")
        else:
            print("Supabase client is NOT initialized!")

        # Process weekly schedule to fix Lab durations and incorrect names
        weekly_schedule = []
        for c_orig in data["weekly_schedule"]:
            c = c_orig.copy() # Work on a copy
            # Extract Course Code (e.g., CS2001)
            course_code_match = re.match(r"^([A-Z]{2,3}\d{4})", c['subject'])
            course_code = course_code_match.group(1) if course_code_match else None

            # Extract Section (e.g., BCS-4B) from subject "CS2006,BCS-4B: ..."
            # Normalize dashes in section: \u2013 is en-dash
            section_match = re.search(r",\s*([A-Za-z0-9\u2013-]+)", c['subject'])
            section = section_match.group(1).strip().upper().replace("\u2013", "-") if section_match else None

            # Check for Live Updates matching this specific class session
            for update in live_data:
                # Normalize values for rock-solid matching
                cur_code = (course_code or "").strip().upper()
                upd_code = (update['course_code'] or "").strip().upper()
                # Normalize update reason: convert en-dashes to hyphens for matching
                upd_reason = (update.get('reason') or "").strip().upper().replace("\u2013", "-")
                upd_text = upd_code + " " + upd_reason
                
                t1 = c['start_time'].lstrip('0').strip()
                t2 = (update.get('original_time') or "").lstrip('0').strip()
                
                # Ramzan Time Mapping (Shifted -> Regular)
                # Emails often use regular times even during Ramzan
                reverse_map = {
                    "9:10": "9:30",
                    "10:20": "11:00",
                    "11:30": "12:30",
                    "3:10": "3:30"
                }
                t1_regular = reverse_map.get(t1, t1)
                
                # Match logic:
                # 1. Course Code MUST match
                # 2. Day MUST match
                # 3. Time MUST match (direct or via regular time mapping) OR use 'ANY' wildcard
                code_match = cur_code == upd_code
                day_match = c['day'] == update['original_day']
                
                # Flexibility for "Today's class is cancelled" without explicit time
                is_any_time = t2.upper() == "ANY"
                time_match = is_any_time or t1.startswith(t2) or t1_regular.startswith(t2) or t2.startswith(t1)

                
                # 4. Section Criteria:
                # If a section is specified in the update, it MUST match the current class's section
                # If no section is found in the update, we fall back to general course-level match
                section_criteria = True
                if section:
                    # Extract potential sections from update text (e.g. BCS-4B, BAI-2A)
                    # We look for patterns like XXX-NX or XXX-N
                    all_sections_in_upd = re.findall(r"([A-Z]{2,4}-[0-9][A-Z]?)", upd_text)
                    
                    if all_sections_in_upd:
                         # The update explicitly mentions some sections.
                         # It must mention OUR section for it to apply to us.
                         section_criteria = (section in all_sections_in_upd)
                    else:
                        # No specific section pattern found, but let's check for direct inclusion 
                        # of the section string (e.g. "BCS-4C") just in case
                        if any(char in upd_text for char in ["-", "–"]): # Optimization
                            if section in upd_text:
                                section_criteria = True
                            elif any(s in upd_text for s in ["BCS", "BSE", "BAI", "BDS"]) and "-" in upd_text:
                                # Reason mentions a section but not ours?
                                # This is tricky. If they say "BCS-4B cancelled" and we are "BCS-4C", we should skip.
                                # Let's stick to the findall for now as it's safer.
                                pass

                if (code_match and day_match and time_match and section_criteria):
                    
                    print(f"MATCH FOUND: {cur_code} on {c['day']} at {c['start_time']}")
                    c['live_status'] = update['status']
                    c['live_reason'] = update['reason']
                    if update['status'] == 'RESCHEDULED':
                        c['live_new_time'] = f"{update.get('new_day', c['day'])} {update.get('new_time', '')}"
                        c['live_new_room'] = update.get('new_room')

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
                    # Set end time - In Ramzan, labs are squashed. 
                    # Two slots of 65 mins + 5 min break = 135 mins = 2h 15m
                    # e.g., 8:00 -> 10:15
                    end_dt = start_dt + timedelta(hours=2, minutes=15)
                    # Update end time string
                    c = c.copy() # Don't mutate original if cached
                    c['end_time'] = end_dt.strftime("%-H:%M") # %-H for no leading zero if possible, or %H
                    if ':' not in c['end_time']: # Fallback for some systems
                         c['end_time'] = end_dt.strftime("%H:%M")
                except Exception as e:
                    print(f"Error fixing lab time: {e}")
            
            weekly_schedule.append(ClassSession(**c))

        # Get current day for "disappearing" logic (Standardize to PKT UTC+5)
        # Vercel is UTC, but campus is PKT.
        pkt_now = datetime.utcnow() + timedelta(hours=5)
        cur_day_idx = pkt_now.weekday()
        day_map = {'Mon':0, 'Tue':1, 'Wed':2, 'Thu':3, 'Fri':4, 'Sat':5, 'Sun':6}
        days_in_week = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

        # Filter live updates for this student vs global campus events
        personal_updates = []
        campus_events = []
        
        # Determine student's course codes
        student_course_codes = []
        for s in weekly_schedule:
            match = re.match(r"^([A-Z]{2,3}\d{4})", s.subject)
            if match:
                student_course_codes.append(match.group(1))

        for l in live_data:
            # Skip if the day has passed (within the current week)
            # NEWS items might have 'N/A' for day, we should show them unless they are old
            update_day = l.get('original_day', 'Mon')[:3]
            if update_day != 'N/A':
                update_day_idx = day_map.get(update_day, 0)
                if update_day_idx < cur_day_idx:
                    continue

            # Populate fields for frontend
            obj = LiveUpdate(**l)
            obj.teacher = obj.extracted_teacher
            obj.description = obj.cleaned_reason

            if l.get('status') in ['EVENT', 'NEWS']:
                campus_events.append(obj)
            else:
                # Class changes: Only include if it matches a student's course code
                upd_code = l.get('course_code', '').strip().upper()
                if upd_code in student_course_codes:
                    personal_updates.append(obj)

        # Format and sort exam schedule
        exam_sessions = []
        for e in data.get("exam_schedule", []):
            try:
                # Input: Mon,23,Feb,26
                dt = datetime.strptime(e["date"], "%a,%d,%b,%y")
                e["date"] = dt.strftime("%a, %d %b %Y")
            except:
                pass
            exam_sessions.append(ExamSession(**e))
            
        # Sort chronologically
        try:
            exam_sessions.sort(key=lambda x: datetime.strptime(x.date, "%a, %d %b %Y") if "," in x.date else datetime.min)
        except:
            pass

        return StudentSchedule(
            roll_number=roll_number,
            weekly_schedule=weekly_schedule,
            exam_schedule=exam_sessions,
            live_updates=personal_updates,
            campus_events=campus_events,
            exam_type=idx.get("exam_type", "Examination Schedule")
        )
    except HTTPException: raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sync")
@app.get("/api/sync")
async def trigger_sync(request_id: Optional[str] = None):
    # Basic security check for Vercel Cron
    # In production, check for a CRON_SECRET header or token
    try:
        import sync_emails
        sync_emails.sync()
        return {"status": "success", "message": "Email sync triggered"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

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
                # Try new format first: Mon, 23 Feb 2026
                try:
                    dt_date = datetime.strptime(exam.date, "%a, %d %b %Y").date()
                except:
                    # Fallback to compact format: Mon,23,Feb,26
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
