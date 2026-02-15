import pdfplumber

def find_instructor_image(pdf_path, page_num, name):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        
        # Find text coordinates
        target_box = None
        for word in page.extract_words():
            if name in word['text']:
                # The name might be split into multiple words
                # For simplicity, just find the line containing the name
                target_box = (word['x0'], word['top'], word['x1'], word['bottom'])
                print(f"Found '{name}' at {target_box}")
                break
        
        if not target_box:
            # Try a broader search
            text = page.extract_text()
            if name in text:
                print(f"Name found in text, but couldn't pinpoint coordinates easily.")
            else:
                print(f"Name '{name}' not found on page.")
                return

        # Find images on this page
        print("\nImages on page:")
        for i, img in enumerate(page.images):
            # Coordinates are (x0, top, x1, bottom)
            # image object has x0, y0, x1, y1 (y is from bottom) or top, bottom?
            # pdfplumber images have x0, top, x1, bottom
            print(f"Image {i+1}: ({img['x0']:.1f}, {img['top']:.1f}, {img['x1']:.1f}, {img['bottom']:.1f})")

if __name__ == "__main__":
    find_instructor_image("PWR Faculty.pdf", 5, "Hafsa")
