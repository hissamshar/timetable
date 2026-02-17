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
        
        mail.logout()
        return recent_emails
    except Exception as e:
        print(f"IMAP Error: {e}")
        return []

def parse_with_ai(email_list):
    if not email_list:
        return []
    
    prompt = f"""
    You are an assistant for a University Timetable app. 
    Analyze the following emails and extract structured information about class cancellations or reschedules.
    
    Format each update as a JSON object with these fields:
    - course_code: (e.g., CS2001)
    - status: (either 'CANCELED' or 'RESCHEDULED')
    - original_day: (Mon, Tue, Wed, Thu, Fri, Sat, Sun)
    - original_time: (HH:MM format, 24-hr)
    - new_day: (if rescheduled, Mon, Tue, etc.)
    - new_time: (if rescheduled, HH:MM format)
    - new_room: (if mentioned)
    - reason: (short reason)

    Emails:
    {json.dumps(email_list)}

    Return ONLY a JSON array of objects. If an email is not about a specific class change, ignore it.
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
        data = json.loads(chat_completion.choices[0].message.content)
        # Ensure it's a list if it's nested under a key like "updates"
        if isinstance(data, dict):
            for key in ["updates", "classes", "events"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
            if "course_code" in data: # Single object
                return [data]
        return data if isinstance(data, list) else []
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
    
    for update in updates:
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
