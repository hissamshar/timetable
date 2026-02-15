import pdfplumber

def inspect_pdf(pdf_path):
    print(f"--- Inspecting {pdf_path} ---")
    with pdfplumber.open(pdf_path) as pdf:
        if len(pdf.pages) > 0:
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            print("First page text:")
            print(text[:1000])  # Print first 1000 chars
            print("\nTable extraction (if any):")
            tables = first_page.extract_tables()
            for i, table in enumerate(tables):
                print(f"Table {i}: {table[:2]}") # Print first 2 rows of each table
        else:
            print("PDF is empty.")
    print("-" * 30)

if __name__ == "__main__":
    inspect_pdf("Student_Timetables V#3 Spring-2026.pdf")
    inspect_pdf("Tentative Datesheet Sessional 1 Spring-2026.pdf")
