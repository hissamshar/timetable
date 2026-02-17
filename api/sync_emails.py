import os
import imaplib
import email
from email.header import decode_header
import json
import re
from datetime import datetime
from supabase import create_client, Client
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Config
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_PASS") # APP PASSWORD
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not all([GMAIL_USER, GMAIL_PASS, SUPABASE_URL, SUPABASE_KEY, GROQ_API_KEY]):
    print("Error: Missing environment variables. Please set GMAIL_USER, GMAIL_PASS, SUPABASE_URL, SUPABASE_KEY, and GROQ_API_KEY in Vercel.")
    exit(1)

# Initialize Clients
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

def get_email_content():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("inbox")

        # Search for emails from university portal or common subjects
        # Adjust search criteria as needed
        status, messages = mail.search(None, '(OR SUBJECT "Reschedule" SUBJECT "Cancelled")')
        
        email_ids = messages[0].split()
        if not email_ids:
            return []

        recent_emails = []
        # Check last 5 relevant emails
        for e_id in email_ids[-5:]:
            res, msg = mail.fetch(e_id, "(RFC822)")
            for response in msg:
                if isinstance(response, tuple):
                    msg = email.message_from_bytes(response[1])
                    subject = decode_header(msg["Subject"])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()
                    
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode()
                    else:
                        body = msg.get_payload(decode=True).decode()
                    
                    recent_emails.append({"subject": subject, "body": body})
                    print(f"Found email: {subject}")
        
        mail.logout()
        return recent_emails
    except Exception as e:
        print(f"IMAP Error: {e}")
        return []

def parse_with_ai(email_list):
    if not email_list:
        return []
    
    today = datetime.now().strftime("%A, %d %B %Y")
    prompt = f"""
    You are an assistant for a University Timetable app. 
    Analyze the following emails and extract structured information about class cancellations or reschedules.
    
    TODAY'S DATE: {today}

    Return a JSON object with a key "updates" containing a list of objects.
    
    STRICT INSTRUCTIONS:
    1. **Class Changes**: Handle cancellations and reschedules as before.
    2. **Campus Events**: Extract society events, seminars, or workshops. 
       - For events, set `status` to 'EVENT'.
       - Use the event title (e.g., 'ACM Coding Contest') as `course_code`.
       - Most events happen on **Wednesday** during the free slot (**11:00 AM - 2:00 PM**) unless specified.
    3. If an email lists multiple sections or days, CREATE A SEPARATE OBJECT FOR EACH.
    4. Each object MUST have these EXACT keys:
       - course_code (string: course code or event title)
       - status (string: 'CANCELED', 'RESCHEDULED', or 'EVENT')
       - original_day (string: Mon, Tue, Wed, Thu, Fri, Sat)
       - original_time (string: HH:MM, mandatory)
       - new_day (optional string)
       - new_time (optional string)
       - new_room (optional string)
       - reason (string: for class changes) / description (string: for events)

    COURSE MAPPING REFERENCE (Class Changes):
    - Probability and Statistics -> MT2005
    - Software Requirements Engineering -> SE3001
    - Cloud Computing -> CS4075
    - Software Design and Architecture -> SE3002
    - Fundamentals of Software Project Management -> SE4002
    - Operating Systems -> CS2006
    - Compiler Construction -> CS4031
    - COAL -> CS2004
    - Database Systems -> CS2005
    - Pakistan Studies -> SS1015
    - Software Engineering -> SE3001
    - Artificial Intelligence -> AI2002

    Emails:
    {json.dumps(email_list)}
    """
    
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a university timetable assistant. Extract structured JSON data from email text."
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
        )
        raw_content = chat_completion.choices[0].message.content
        print(f"Raw AI Response: {raw_content}")
        data = json.loads(raw_content)
        updates = []
        # Ensure it's a list if it's nested under a key like "updates"
        if isinstance(data, dict):
            for key in ["updates", "classes", "events"]:
                if key in data and isinstance(data[key], list):
                    updates = data[key]
                    break
            if not updates and "course_code" in data:
                updates = [data]
        elif isinstance(data, list):
            updates = data

        # Post-process updates
        day_map = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun"}
        processed = []
        for u in updates:
            # Normalize Day
            u["original_day"] = day_map.get(u.get("original_day"), u.get("original_day"))
            if u["original_day"] not in day_map.values():
                continue # Skip invalid days
            
            # Normalize Time (e.g., "9:30 AM" -> "9:30")
            time_match = re.search(r"(\d{1,2}:\d{2})", u.get("original_time", ""))
            if time_match:
                u["original_time"] = time_match.group(1)
            else:
                continue # Skip if no time found
            
            processed.append(u)
        return processed
    except Exception as e:
        print(f"Groq Error: {e}")
        return []

def sync():
    print("Fetching emails...")
    emails = get_email_content()
    if not emails:
        print("No relevant emails found.")
        return

    print(f"Processing {len(emails)} emails with AI...")
    updates = parse_with_ai(emails)
    print(f"AI returned {len(updates)} updates.")
    
    for update in updates:
        print(f"Applying update for {update.get('course_code')}...")
        try:
            # Check if this update already exists (prevent duplicates)
            existing = supabase.table("live_updates")\
                .select("*")\
                .eq("course_code", update["course_code"])\
                .eq("original_day", update["original_day"])\
                .eq("original_time", update["original_time"])\
                .execute()
            
            if not existing.data:
                supabase.table("live_updates").insert(update).execute()
                print(f"Inserted update for {update['course_code']}")
            else:
                print(f"Update for {update['course_code']} already exists.")
        except Exception as e:
            print(f"Database Error: {e}")

if __name__ == "__main__":
    sync()
