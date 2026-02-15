import pdfplumber

def test_extract(path):
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        text = page.extract_text()
        words = page.extract_words()
        print(f"Text length: {len(text) if text else 0}")
        print(f"Words count: {len(words)}")
        if text:
            print("--- TEXT ---")
            print(text[:500])
        if words:
            print("--- FIRST 5 WORDS ---")
            print(words[:5])

if __name__ == "__main__":
    test_extract("SP-2026 Academic Plan.pdf")
