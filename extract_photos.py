import pdfplumber
import os

def extract_images(pdf_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            for j, image in enumerate(page.images):
                # Extract image box
                bbox = (image['x0'], image['top'], image['x1'], image['bottom'])
                page_obj = page.within_bbox(bbox)
                
                # Save crop as image
                img = page_obj.to_image(resolution=300)
                img_path = os.path.join(output_dir, f"page_{i+1}_img_{j+1}.png")
                img.save(img_path)
                print(f"Saved {img_path}")

if __name__ == "__main__":
    extract_images("PWR Faculty.pdf", "extracted_photos")
