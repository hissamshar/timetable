import json
import os
import shutil

# Paths
DATA_FILE = '/home/hisam/timetable/exam_scheduler_pro/api/schedules_index.json'
BACKUP_FILE = '/home/hisam/timetable/exam_scheduler_pro/api/schedules_index_regular.json'

# Ramzan Timings Mapping
# Old Start Time -> (New Start Time, New End Time)
TIME_MAPPING = {
    "8:00": ("8:00", "9:05"),
    "9:30": ("9:10", "10:15"),
    "11:00": ("10:20", "11:25"),
    "12:30": ("11:30", "12:35"),
    "2:00": ("2:00", "3:05"),
    "3:30": ("3:10", "4:15"),
    # Handling potential variations or typos in JSON if any
    "08:00": ("8:00", "9:05"),
    "09:30": ("9:10", "10:15"),
    "14:00": ("2:00", "3:05"),
    "15:30": ("3:10", "4:15")
}

def update_timetable():
    if not os.path.exists(DATA_FILE):
        print(f"Error: {DATA_FILE} not found.")
        return

    # 1. Create Backup if it likely contains regular timings
    # We check if we already have a backup. If not, we assume current is regular.
    # If backup exists, we assume current might already be modified, but user asked to update "info from this timetable"
    # User said "make backup of previous".
    
    if not os.path.exists(BACKUP_FILE):
        print(f"Creating backup of regular timetable at {BACKUP_FILE}")
        shutil.copy(DATA_FILE, BACKUP_FILE)
    else:
        print(f"Backup already exists at {BACKUP_FILE}. Using it as source for regular timings to be safe?")
        # Ideally we should read from the regular one to apply transformation, 
        # to avoid double transformation if script is run twice.
        # But if the current file IS the regular one (just backed up), we modify the current file.
        pass

    # Load data
    # We will load from the BACKUP to ensure we are applying Ramzan timings to the Original timings.
    # This prevents issues if we run the script multiple times (mapping 8:00->8:00 is fine, but 11:00->10:20->???)
    # So always source from regular backup.
    
    print(f"Loading data from {BACKUP_FILE}...")
    with open(BACKUP_FILE, 'r') as f:
        data = json.load(f)

    updated_count = 0
    unknown_slots = set()

    schedules = data.get("schedules", {})
    
    for student_id, student_data in schedules.items():
        weekly = student_data.get("weekly_schedule", [])
        for slot in weekly:
            start = slot.get("start_time")
            # Normalize start time slightly (strip whitespace)
            if start:
                start = start.strip()
            
            if start in TIME_MAPPING:
                new_start, new_end = TIME_MAPPING[start]
                slot["start_time"] = new_start
                slot["end_time"] = new_end
                updated_count += 1
            else:
                # Keep track of unmapped slots to report
                unknown_slots.add(start)

    # Save to DATA_FILE (The active file)
    print(f"Saving updated Ramzan timetable to {DATA_FILE}...")
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Update complete. {updated_count} slots updated.")
    if unknown_slots:
        print(f"Warning: The following start times were not mapped: {unknown_slots}")

if __name__ == "__main__":
    update_timetable()
