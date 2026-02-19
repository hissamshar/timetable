from datetime import datetime
import re

def test_filter():
    live_data = [
        {'id': 'f8c68568-8737-4c2f-b096-cc46da82fe6c', 'created_at': '2026-02-17T13:50:04.469767+00:00', 'course_code': 'SE3001', 'status': 'CANCELED', 'original_day': 'Tue', 'original_time': '9:30', 'new_day': None, 'new_time': None, 'new_room': None, 'reason': 'SRE Class (BS-SE 4A) cancelled', 'expires_at': None},
        {'id': '0b9d5434-17d9-4ad7-b03a-2841127fc221', 'created_at': '2026-02-17T13:50:06.970747+00:00', 'course_code': 'MT2005', 'status': 'CANCELED', 'original_day': 'Wed', 'original_time': '9:30', 'new_day': None, 'new_time': None, 'new_room': None, 'reason': 'Probability and Statistics (BCS–4A) cancelled', 'expires_at': None}
    ]
    
    day_map = {'Mon':0, 'Tue':1, 'Wed':2, 'Thu':3, 'Fri':4, 'Sat':5, 'Sun':6}
    # Forcing cur_day_idx to 3 (Thursday)
    cur_day_idx = 3 
    
    personal_updates = []
    # Simplified course codes for test
    student_course_codes = ['MT2005', 'SE3001']

    for l in live_data:
        update_day = l.get('original_day', 'Mon')[:3]
        if update_day != 'N/A':
            update_day_idx = day_map.get(update_day, 0)
            print(f"Checking {l['course_code']} ({update_day}): {update_day_idx} < {cur_day_idx}")
            if update_day_idx < cur_day_idx:
                print(f"Skipping {l['course_code']}")
                continue
        personal_updates.append(l)

    print(f"Result: {len(personal_updates)} updates remaining.")

if __name__ == "__main__":
    test_filter()
