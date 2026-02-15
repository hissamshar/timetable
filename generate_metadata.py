import pdfplumber
import re
import json
import os

TIMETABLE_DIR = "/home/hisam/timetable"
TEACHERS_PDF = os.path.join(TIMETABLE_DIR, "Teachers_Timetables_V#4 Spring-2026.pdf")
LOCATIONS_PDF = os.path.join(TIMETABLE_DIR, "Locatiowise Timetable_V#4 Spring-2026.pdf")
OUTPUT_FILE = "/home/hisam/timetable/exam_scheduler_pro/metadata.json"

def extract_teachers():
    teachers = set()
    if not os.path.exists(TEACHERS_PDF):
        return []
    
    with pdfplumber.open(TEACHERS_PDF) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            # Pattern: Timetable Report: Name optionalNumber
            match = re.search(r'Timetable Report:\s*(.+?)(?:\s+\d|$)', text)
            if match:
                teachers.add(match.group(1).strip())
    
    return sorted(list(teachers))

def extract_venues():
    venues = set()
    if not os.path.exists(LOCATIONS_PDF):
        return []
    
    with pdfplumber.open(LOCATIONS_PDF) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            # Pattern: Timetable for Venue: Name
            match = re.search(r'Timetable for Venue:\s*(.+)', text)
            if match:
                venues.add(match.group(1).split('\n')[0].strip())
    
    return sorted(list(venues))

def main():
    print("Extracting teachers...")
    teachers = extract_teachers()
    print(f"Found {len(teachers)} teachers.")
    
    print("Extracting venues...")
    venues = extract_venues()
    print(f"Found {len(venues)} venues.")
    
    # Create room mapping dictionary
    # Example: "Hassan Abidi" -> "Hassan Abidi Hall/Lab"
    # We can use the venues as "proper names" and derive aliases
    room_aliases = {}
    for v in venues:
        # Simple alias: if it contains "Lab" or "Hall", the name before it is an alias
        name = v.lower()
        room_aliases[name] = v
        
        # Handle "Room X"
        if "room" in name:
            short = name.replace("room", "").strip()
            if short: room_aliases[short] = v
            if short.isdigit(): room_aliases[f"r{short}"] = v
        
        # Handle "X/Y Lab" -> "X", "Y", "X/Y"
        base_name = name.replace("lab", "").strip().strip('/')
        if base_name:
            room_aliases[base_name] = v
            parts = re.split(r'[/ .]', base_name)
            for p in parts:
                p = p.strip()
                if p and len(p) > 2:
                    room_aliases[p] = v

    metadata = {
        "teachers": teachers,
        "venues": venues,
        "room_aliases": room_aliases
    }
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Metadata saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
