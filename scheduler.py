from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, time

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
    room: Optional[str] = None # Room might not be in tentative datesheet

class StudentSchedule(BaseModel):
    roll_number: str
    weekly_schedule: List[ClassSession]
    exam_schedule: List[ExamSession]
    exam_type: Optional[str] = None
    generated_at: datetime = datetime.now()
