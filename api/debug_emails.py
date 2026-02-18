import imaplib
import email
from email.header import decode_header
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_PASS")

def debug_emails():
    try:
        print(f"Connecting to imap.gmail.com as {GMAIL_USER}...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("inbox")

        today_imap = datetime.now().strftime("%d-%b-%Y")
        print(f"Searching for emails since {today_imap}...")
        status, messages = mail.search(None, f'(SINCE "{today_imap}")')
        
        email_ids = messages[0].split()
        print(f"Found {len(email_ids)} emails since today.")
        
        if not email_ids:
            return

        for e_id in email_ids[-20:]:
            res, msg = mail.fetch(e_id, "(RFC822)")
            for response in msg:
                if isinstance(response, tuple):
                    msg = email.message_from_bytes(response[1])
                    subject = decode_header(msg["Subject"])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()
                    print(f"Subject: {subject}")
        
        mail.logout()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_emails()
