import pdfplumber

student_pdf = "Student_Timetables V#5 Spring-2026.pdf"
exam_pdf = "Final DateSheet Sessional 2 Spring-2026.pdf"

print("--- STUDENT TIMETABLE (First 2 Pages Structure) ---")
with pdfplumber.open(student_pdf) as pdf:
    for i, page in enumerate(pdf.pages[:2]):
        print(f"Page {i+1}")
        text = page.extract_text()
        print(text)
        print("TABLES:", len(page.extract_tables()))

print("--- EXAM DATESHEET (First 2 Pages Structure) ---")
with pdfplumber.open(exam_pdf) as pdf:
    for i, page in enumerate(pdf.pages[:2]):
        print(f"Page {i+1}")
        text = page.extract_text()
        print(text[:1000])  # Just part of it
        print("TABLES:", len(page.extract_tables()))
