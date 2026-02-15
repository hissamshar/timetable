import json
import os
import re
from difflib import SequenceMatcher

DESIGNATIONS = ["Professor", "Lecturer", "Instructor", "Lab Engineer", "Incharge", "Director", "Incharge (CS)", "Incharge (SH)", "Coordinator", "Director"]

def normalize_name(name):
    name = re.sub(r'^(Dr\.|Mr\.|Ms\.|Mrs\.|Syed|S\.|Mr|Ms|Dr)\s+', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\(.*?\)', '', name)
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    name = name.strip(' .,;:')
    return name.strip().lower()

def is_valid_name(name):
    if len(name) < 4 or len(name) > 50: return False
    # If it's a known designation, it's NOT a name line for our parsing purposes
    if any(d in name for d in DESIGNATIONS): return False
    if re.search(r'\d', name): return False
    if "(" in name or ")" in name: return False
    if ' ' not in name and len(name) > 15: return False
    if any(kw in name.upper() for kw in ["PHD", "MPHIL", "MSC", "MCS", "BBA", "BTECH", "QUALIFICATIONS"]): return False
    return True

def find_best_match(norm_name, lookup):
    if norm_name in lookup:
        return norm_name
    for existing_norm in lookup:
        ratio = SequenceMatcher(None, norm_name, existing_norm).ratio()
        if ratio > 0.85:
            return existing_norm
    return None

def parse_ocr_text(ocr_dir):
    extracted_faculty = []
    current_dept = "Unknown"
    
    files = sorted([f for f in os.listdir(ocr_dir) if f.endswith('.txt')])
    
    for filename in files:
        with open(os.path.join(ocr_dir, filename), 'r') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            
            i = 0
            while i < len(lines):
                line = lines[i]
                if "Department of" in line:
                    current_dept = line.split("Department of")[-1].strip()
                    i += 1
                    continue
                
                if is_valid_name(line):
                    name = line
                    designation = "Faculty"
                    qualifications = []
                    
                    j = i + 1
                    while j < len(lines) and j < i + 8:
                        next_line = lines[j]
                        if "Department of" in next_line: break
                        if is_valid_name(next_line): break
                        
                        if any(kw in next_line for kw in DESIGNATIONS):
                            designation = next_line
                        elif any(kw in next_line for kw in ["PhD", "MS", "BS", "MSc", "MCS", "MPhil", "BSc", "MA", "BBA"]):
                            qualifications.append(next_line)
                        j += 1
                    
                    extracted_faculty.append({
                        "raw_name": name,
                        "normalized_name": normalize_name(name),
                        "designation": designation,
                        "department": current_dept,
                        "qualifications": qualifications
                    })
                    i = j - 1
                i += 1
    return extracted_faculty

def merge_data(existing_path, extracted_list):
    with open(existing_path, 'r') as f:
        existing_data = json.load(f)
    
    lookup = {normalize_name(f["name"]): f for f in existing_data}
    
    new_entries = 0
    updated_entries = 0
    
    for ext in extracted_list:
        norm_name = ext["normalized_name"]
        match = find_best_match(norm_name, lookup)
        
        if match:
            fac = lookup[match]
            if fac.get("designation") == "Faculty" or not fac.get("designation") or fac.get("designation") == "":
                fac["designation"] = ext["designation"]
                updated_entries += 1
            if fac.get("department") == "Unknown" or not fac.get("department") or fac.get("department") == "":
                fac["department"] = ext["department"]
            fac["qualifications"] = ext["qualifications"]
        else:
            new_fac = {
                "id": f"ext_{new_entries + 1000}",
                "name": ext["raw_name"],
                "designation": ext["designation"],
                "department": ext["department"],
                "email": "",
                "phone": "",
                "photo_url": "",
                "photo_local": "",
                "profile_url": "",
                "qualifications": ext["qualifications"]
            }
            existing_data.append(new_fac)
            new_entries += 1
            lookup[norm_name] = new_fac
            
    with open(existing_path, 'w') as f:
        json.dump(existing_data, f, indent=2)
    
    return new_entries, updated_entries

if __name__ == "__main__":
    ocr_results = parse_ocr_text("temp_faculty_images")
    new_cnt, upd_cnt = merge_data("faculty_data.json", ocr_results)
    print(f"Merge Complete: {new_cnt} new added, {upd_cnt} updated.")
