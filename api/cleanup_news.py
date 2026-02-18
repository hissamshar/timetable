from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def cleanup_duplicates():
    print("Fetching news items for cleanup...")
    res = supabase.table("live_updates").select("*").eq("status", "NEWS").execute()
    data = res.data
    
    if not data:
        print("No news items found.")
        return

    # Group by teacher and find similarities
    to_delete = []
    seen_topics = {} # teacher -> [list of topics]
    
    for item in data:
        # Extract teacher from the reason field: "[Teacher Name] Description"
        import re
        reason = item.get("reason", "")
        match = re.search(r"^\[(.*?)\]", reason)
        teacher = match.group(1) if match else "Unknown"
        
        title = item["course_code"].lower()
        topic_match = False
        
        if teacher not in seen_topics:
            seen_topics[teacher] = []
        
        for seen_title in seen_topics[teacher]:
            if title in seen_title or seen_title in title or title[:15] == seen_title[:15]:
                topic_match = True
                break
        
        if topic_match:
            print(f"Found duplicate: {item['course_code']} (Teacher: {teacher})")
            to_delete.append(item["id"])
        else:
            seen_topics[teacher].append(title)
            
    if to_delete:
        print(f"Deleting {len(to_delete)} duplicate entries...")
        for d_id in to_delete:
            supabase.table("live_updates").delete().eq("id", d_id).execute()
        print("Cleanup complete.")
    else:
        print("No duplicates found to clean.")

if __name__ == "__main__":
    cleanup_duplicates()
