import pdfplumber
import os
import subprocess
from PIL import Image
import io

def extract_and_ocr(pdf_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    with pdfplumber.open(pdf_path) as pdf:
        img_count = 0
        for i, page in enumerate(pdf.pages):
            print(f"Processing page {i+1}...")
            # We can also just take a screenshot of the page if images are tricky
            # But let's try extracting the image objects first.
            # If the PDF is just an image, page.to_image() is easier.
            
            p_img = page.to_image(resolution=300)
            img_path = os.path.join(output_dir, f"page_{i+1}.png")
            p_img.save(img_path)
            
            # Run OCR on the page image
            print(f"  Running OCR on page {i+1}...")
            ocr_text_path = os.path.join(output_dir, f"page_{i+1}")
            subprocess.run(["tesseract", img_path, ocr_text_path], check=True)
            
            with open(ocr_text_path + ".txt", "r") as f:
                text = f.read()
                print(f"  Extracted {len(text)} characters from page {i+1}")

if __name__ == "__main__":
    extract_and_ocr("PWR Faculty.pdf", "temp_faculty_images")
