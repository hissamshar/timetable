from groq import Groq
import json
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

def test_ai():
    email_list = [
        {
            "subject": "Fwd: GenAI (AI4009) Lecture Cancelled today --- Section (BAI-8A)",
            "body": "Dear Students Today's Lecture of GenAI is cancelled. It will be rescheduled on a later date. regards Dr. Muhammad Tahir Professor..."
        }
    ]
    
    prompt = f"""
    Analyze the following emails and extract structured information about class cancellations or reschedules.
    
    TODAY'S DATE: Wednesday, 18 February 2026

    Return a JSON object with a key "updates".
    
    COURSE MAPPING REFERENCE:
    - GenAI -> AI4009
    
    Strictly find the Teacher's Name. If it is Muhammad Tahir, extract it.
    If no time is mentioned but it says "Today's Lecture", use "ANY".

    Emails:
    {json.dumps(email_list)}
    """
    
    chat_completion = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"},
    )
    print(chat_completion.choices[0].message.content)

if __name__ == "__main__":
    test_ai()
