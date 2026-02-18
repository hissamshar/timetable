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

        # Get today's date in IMAP format (01-Jan-2024)
        today_imap = datetime.now().strftime("%d-%b-%Y")
        
        # Only search for today's emails
        status, messages = mail.search(None, f'(SINCE "{today_imap}")')
        
        email_ids = messages[0].split()
        if not email_ids:
            return []

        recent_emails = []
        # Check last 30 relevant emails to ensure we don't miss anything
        for e_id in email_ids[-30:]:
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
    1. **Class Changes**: Handle cancellations and reschedules.
       - Extract the **Teacher's Name** from the signature or text.
    2. **Campus Events**: Society events, seminars, or workshops. 
       - Set `status` to 'EVENT'.
       - Use the event title as `course_code`.
       - Events on **Wednesday** during the free slot (**11:00 AM - 2:00 PM**) are common; check if they are mentioned.
    3. If an email lists multiple sections or days, CREATE A SEPARATE OBJECT FOR EACH.
    4. Each object MUST have these EXACT keys:
       - course_code (string: course code, event title, or short news headline)
       - teacher (string: Name of the professor or society lead who sent the email)
       - status (string: 'CANCELED', 'RESCHEDULED', 'EVENT', or 'NEWS')
       - original_day (string: Mon, Tue, Wed, Thu, Fri, Sat, or 'N/A' for News)
       - original_time (string: HH:MM, mandatory for classes, 'ANY' for today's classes, or 'N/A' for News)
       - new_day (optional string)
       - new_time (optional string)
       - new_room (optional string)
       - reason (string: for class changes) / description (string: for events and news)

    NEWS & ANNOUNCEMENT INSTRUCTIONS:
    - If an email is about a deadline, feedback form, registration, or general info (not a class time change).
    - Set `status` to 'NEWS'.
    - Use a catchy short headline as `course_code`.
    - Use 'N/A' for `original_day` and `original_time`.

    COURSE MAPPING REFERENCE (Class Changes):
    - Probability and Statistics -> MT2005
    - Probability & Statistics -> MT2005
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
    - Generative AI -> AI4009
    - GenAI -> AI4009

    PROACTIVE TEACHER EXTRACTION:
    - Look closely at the signature (end of email).
    - Look for "Warm regards,", "Regards,", "Best,", "Thanks,", etc. followed by a name.
    - If the email is forwarded, look for the 'From:' field within the body.
    - DO NOT return 'Unknown' if there is ANY name present that looks like an instructor.
    - If no name is found at all, look for the course name/code and guess if possible, but prioritize finding the actual name.

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
        print(f"AI Response: {raw_content}")
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
            if u.get("status") == "NEWS":
                u["original_day"] = "N/A"
            else:
                u["original_day"] = day_map.get(u.get("original_day"), u.get("original_day"))
                if u["original_day"] not in day_map.values():
                    continue # Skip invalid days
            
            # Normalize Time (e.g., "9:30 AM" -> "9:30")
            if u.get("status") == "NEWS":
                u["original_time"] = "N/A"
            else:
                time_match = re.search(r"(\d{1,2}:\d{2})", str(u.get("original_time", "")))
                if time_match:
                    u["original_time"] = time_match.group(1)
                elif any(keyword in (u.get("reason", "") + u.get("status", "")).lower() for keyword in ["today", "cancel", "canceled", "cancelled"]):
                    # If no time is found but it's a cancellation for "today", use 'ANY'
                    u["original_time"] = "ANY"
                else:
                    continue # Skip if no time found and not clearly 'today'

            # Map teacher and description into the existing 'reason' column
            teacher = u.pop("teacher", "Unknown")
            description = u.pop("description", "")
            orig_reason = u.get("reason", "")
            u["reason"] = f"[{teacher}] {description or orig_reason}".strip()
            
            processed.append(u)
        return processed
    except Exception as e:
        print(f"Groq Error: {e}")
        return []

def sync():
    print("Fetching emails...")
    all_emails = get_email_content()
    if not all_emails:
        print("No relevant emails found.")
        return

    # Filter for relevant emails to save tokens
    keywords = ["cancel", "resched", "lecture", "class", "meeting", "event", "venue", "room", "timetable", "schedule", "feedback", "registration", "deadline", "opening", "survey", "form"]
    relevant_emails = []
    for e in all_emails:
        subj = e["subject"].lower()
        if any(kw in subj for kw in keywords):
            relevant_emails.append(e)
    
    if not relevant_emails:
        print("No relevant emails after filtering.")
        return

    # Take the last 15 relevant emails and process in batches of 7 to avoid TPM limits
    # (Groq llama-3.3-70b has approx 12k TPM limit)
    to_process = relevant_emails[-15:]
    print(f"Processing {len(to_process)} relevant emails in batches...")
    
    all_updates = []
    for i in range(0, len(to_process), 7):
        batch = to_process[i:i+7]
        print(f"Processing batch of {len(batch)} emails...")
        batch_updates = parse_with_ai(batch)
        all_updates.extend(batch_updates)

    print(f"Total AI returned {len(all_updates)} updates.")
    
    for update in all_updates:
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
