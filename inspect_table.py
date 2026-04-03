import pdfplumber

student_pdf = "Student_Timetables V#5 Spring-2026.pdf"
with pdfplumber.open(student_pdf) as pdf:
    for i, page in enumerate(pdf.pages[:1]):
        tables = page.extract_tables()
        print("Num tables:", len(tables))
        import pprint
        pprint.pprint(tables)
