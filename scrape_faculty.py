"""
Scrape faculty data from FAST-NUCES Peshawar website.
Downloads profile pictures and saves structured data as JSON.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import time

FACULTY_PAGES = [
    ("https://pwr.nu.edu.pk/cs-faculty/", "Computing"),
    ("https://pwr.nu.edu.pk/ee-faculty/", "Electrical Engineering"),
    ("https://pwr.nu.edu.pk/ss-faculty/", "Social Sciences"),
    ("https://pwr.nu.edu.pk/ms-faculty/", "Management Sciences"),
]

PHOTO_DIR = os.path.join(os.path.dirname(__file__), "frontend", "public", "faculty")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "faculty_data.json")


def scrape_faculty_page(url, department):
    """Scrape a single faculty listing page."""
    faculty = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠ Failed to fetch {url}: {e}")
        return []
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Find all links to faculty profile pages
    profile_links = soup.find_all("a", href=re.compile(r"faculty-profile\.php\?id=\d+"))
    processed_ids = set()
    
    for link in profile_links:
        href = link.get("href", "")
        id_match = re.search(r"id=(\d+)", href)
        if not id_match:
            continue
        fac_id = id_match.group(1)
        if fac_id in processed_ids:
            continue
        processed_ids.add(fac_id)
        
        name = link.get_text(strip=True)
        if not name or len(name) < 3:
            continue
        
        # Find the parent container (card)
        container = link.find_parent("div", class_=re.compile(r"col-"))
        if not container:
            container = link.parent.parent.parent
        
        all_text = container.get_text("\n", strip=True) if container else ""
        lines = [l.strip() for l in all_text.split("\n") if l.strip()]
        
        # Extract email
        email = ""
        email_tag = container.find("a", href=re.compile(r"mailto:")) if container else None
        if email_tag:
            email = email_tag.get("href", "").replace("mailto:", "")
        else:
            email_match = re.search(r"([a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z]+)", all_text)
            if email_match:
                email = email_match.group(1)
        
        # Extract designation
        designation = ""
        for line in lines:
            if any(kw in line for kw in ["Professor", "Lecturer", "Instructor", "Lab Engineer", "Teaching Fellow"]):
                designation = line
                break
        
        # HEC approved?
        hec = any("HEC" in line or "Approved" in line for line in lines)
        if hec and designation:
            designation += " (HEC Approved PhD Supervisor)"
        
        # Phone extension
        phone = ""
        for line in lines:
            ext_match = re.search(r"Ext\.?\s*(\d+)", line, re.IGNORECASE)
            if ext_match:
                phone = f"+92 (091) 111 128 128 Ext. {ext_match.group(1)}"
                break
        
        # Photo URL
        img = container.find("img") if container else None
        if img and img.get("src"):
            photo_url = img["src"]
            if not photo_url.startswith("http"):
                photo_url = f"https://pwr.nu.edu.pk{photo_url}" if photo_url.startswith("/") else f"https://pwr.nu.edu.pk/{photo_url}"
        else:
            photo_url = f"https://pwr.nu.edu.pk/images/faculty/thumb{fac_id}.jpg"
        
        # Full profile URL
        if not href.startswith("http"):
            profile_url = f"https://pwr.nu.edu.pk/cs-faculty/{href}" if not href.startswith("/") else f"https://pwr.nu.edu.pk{href}"
        else:
            profile_url = href
        
        faculty.append({
            "id": fac_id,
            "name": name,
            "designation": designation or "Faculty",
            "department": department,
            "email": email,
            "phone": phone,
            "photo_url": photo_url,
            "photo_local": f"/faculty/thumb{fac_id}.jpg",
            "profile_url": profile_url,
        })
    
    return faculty


def download_photos(faculty_list):
    """Download profile photos for all faculty."""
    os.makedirs(PHOTO_DIR, exist_ok=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }
    
    downloaded = 0
    skipped = 0
    failed = 0
    
    for fac in faculty_list:
        filename = f"thumb{fac['id']}.jpg"
        filepath = os.path.join(PHOTO_DIR, filename)
        
        if os.path.exists(filepath):
            skipped += 1
            continue
        
        try:
            resp = requests.get(fac["photo_url"], headers=headers, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 500:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                downloaded += 1
            else:
                failed += 1
                print(f"  ⚠ No photo for {fac['name']} (status {resp.status_code})")
        except Exception as e:
            failed += 1
            print(f"  ⚠ Failed to download photo for {fac['name']}: {e}")
        
        time.sleep(0.2)  # Be polite
    
    print(f"  📷 Photos: {downloaded} downloaded, {skipped} already existed, {failed} failed")


def main():
    all_faculty = []
    
    for url, dept in FACULTY_PAGES:
        print(f"🔍 Scraping {dept} faculty from {url}...")
        faculty = scrape_faculty_page(url, dept)
        print(f"  ✅ Found {len(faculty)} faculty members")
        all_faculty.extend(faculty)
    
    print(f"\n📊 Total faculty: {len(all_faculty)}")
    
    # Download photos
    print("\n📥 Downloading profile photos...")
    download_photos(all_faculty)
    
    # Save to JSON
    with open(OUTPUT_FILE, "w") as f:
        json.dump(all_faculty, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Saved faculty data to {OUTPUT_FILE}")
    
    # Print some stats
    with_email = sum(1 for f in all_faculty if f["email"])
    with_phone = sum(1 for f in all_faculty if f["phone"])
    print(f"  📧 With emails: {with_email}/{len(all_faculty)}")
    print(f"  📞 With phone: {with_phone}/{len(all_faculty)}")


if __name__ == "__main__":
    main()
