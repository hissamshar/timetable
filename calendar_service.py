import datetime
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import pickle
from typing import List, Optional
from scheduler import ClassSession, ExamSession

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']
REDIRECT_URI = 'http://localhost:8000/auth/callback'

class CalendarService:
    def __init__(self, token_path='token.json', credentials_path='credentials.json'):
        self.creds = None
        self.service = None
        self.token_path = token_path
        self.credentials_path = credentials_path
        
        # Load credentials if exist
        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            except Exception:
                self.creds = None
        
        # Refresh if expired
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                with open(self.token_path, 'w') as token:
                    token.write(self.creds.to_json())
            except Exception:
                self.creds = None
        
        if self.creds and self.creds.valid:
             self.service = build('calendar', 'v3', credentials=self.creds)

    def is_authenticated(self) -> bool:
        return self.creds is not None and self.creds.valid

    def get_auth_url(self) -> str:
        if not os.path.exists(self.credentials_path):
            raise Exception("credentials.json not found.")
            
        flow = Flow.from_client_secrets_file(
            self.credentials_path,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url

    def exchange_code(self, code: str):
        if not os.path.exists(self.credentials_path):
             raise Exception("credentials.json not found.")
             
        flow = Flow.from_client_secrets_file(
            self.credentials_path,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)
        self.creds = flow.credentials
        
        # Save credentials
        with open(self.token_path, 'w') as token:
            token.write(self.creds.to_json())
            
        self.service = build('calendar', 'v3', credentials=self.creds)

    def create_calendar(self, calendar_name: str) -> str:
        if not self.service: raise Exception("Not authenticated")
        
        # Check if exists
        page_token = None
        while True:
            calendar_list = self.service.calendarList().list(pageToken=page_token).execute()
            for calendar_list_entry in calendar_list['items']:
                if calendar_list_entry['summary'] == calendar_name:
                    return calendar_list_entry['id']
            page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break
        
        # Create new
        calendar = {
            'summary': calendar_name,
            'timeZone': 'Asia/Karachi'
        }
        created_calendar = self.service.calendars().insert(body=calendar).execute()
        return created_calendar['id']

    def add_weekly_classes(self, calendar_id: str, classes: List[ClassSession], semester_start: datetime.date, semester_weeks: int = 16):
        if not self.service: raise Exception("Not authenticated")
        
        day_map = {
            "Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6
        }
        
        for cls in classes:
            day_num = day_map.get(cls.day)
            if day_num is None: continue
            
            days_ahead = day_num - semester_start.weekday()
            if days_ahead < 0: days_ahead += 7
            first_date = semester_start + datetime.timedelta(days=days_ahead)
            
            start_dt = datetime.datetime.combine(first_date, datetime.datetime.strptime(cls.start_time, "%H:%M").time())
            end_dt = datetime.datetime.combine(first_date, datetime.datetime.strptime(cls.end_time, "%H:%M").time())
            
            event = {
                'summary': cls.subject,
                'location': cls.room,
                'description': f'Teacher: {cls.teacher}',
                'start': {
                    'dateTime': start_dt.isoformat(),
                    'timeZone': 'Asia/Karachi',
                },
                'end': {
                    'dateTime': end_dt.isoformat(),
                    'timeZone': 'Asia/Karachi',
                },
                'recurrence': [
                    f'RRULE:FREQ=WEEKLY;COUNT={semester_weeks}'
                ],
            }
            
            try:
                self.service.events().insert(calendarId=calendar_id, body=event).execute()
            except Exception as e:
                print(f"Error adding class {cls.subject}: {e}")

    def add_exams(self, calendar_id: str, exams: List[ExamSession]):
        if not self.service: raise Exception("Not authenticated")
        
        for exam in exams:
            try:
                clean_date = exam.date.replace(" ", "")
                dt_date = datetime.datetime.strptime(clean_date, "%a,%d,%b,%y").date()
                
                start_dt = datetime.datetime.combine(dt_date, datetime.datetime.strptime(exam.start_time, "%H:%M").time())
                end_dt = datetime.datetime.combine(dt_date, datetime.datetime.strptime(exam.end_time, "%H:%M").time())
                
                event = {
                    'summary': f"EXAM: {exam.subject}",
                    'description': "MidTerm / Final Exam",
                    'start': {
                        'dateTime': start_dt.isoformat(),
                        'timeZone': 'Asia/Karachi',
                    },
                    'end': {
                        'dateTime': end_dt.isoformat(),
                        'timeZone': 'Asia/Karachi',
                    },
                    'colorId': '11' 
                }
                
                self.service.events().insert(calendarId=calendar_id, body=event).execute()
                
            except Exception as e:
                print(f"Error adding exam {exam.subject}: {e}")
