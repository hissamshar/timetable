import imaplib
import email
from email.header import decode_header
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_PASS")

def debug_announcement():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("inbox")
        status, messages = mail.search(None, f'SUBJECT "Today I\'m not feeling well so class is"')
        email_ids = messages[0].split()
        if not email_ids:
            print("Not found")
            return

        res, msg = mail.fetch(email_ids[-1], "(RFC822)")
        for response in msg:
            if isinstance(response, tuple):
                msg = email.message_from_bytes(response[1])
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode()
                else:
                    body = msg.get_payload(decode=True).decode()
                print(f"Body: {body}")
        mail.logout()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_announcement()
