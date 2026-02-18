import os
import shutil

DATA_FILE = '/home/hisam/timetable/exam_scheduler_pro/api/schedules_index.json'
BACKUP_FILE = '/home/hisam/timetable/exam_scheduler_pro/api/schedules_index_regular.json'

def revert_timetable():
    if not os.path.exists(BACKUP_FILE):
        print(f"Error: Regular timetable backup {BACKUP_FILE} not found. Cannot revert.")
        return

    print(f"Restoring regular timetable from {BACKUP_FILE}...")
    shutil.copy(BACKUP_FILE, DATA_FILE)
    print("Revert complete. The timetable is back to regular timings.")

if __name__ == "__main__":
    revert_timetable()
