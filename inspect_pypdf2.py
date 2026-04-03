import PyPDF2

student_pdf = "Student_Timetables V#5 Spring-2026.pdf"
exam_pdf = "Final DateSheet Sessional 2 Spring-2026.pdf"

print("--- STUDENT TIMETABLE (First 2 Pages Structure) ---")
with open(student_pdf, "rb") as f:
    reader = PyPDF2.PdfReader(f)
    for i in range(min(2, len(reader.pages))):
        print(f"Page {i+1}")
        text = reader.pages[i].extract_text()
        print(text[:1000] + "\n...\n")

print("--- EXAM DATESHEET (First Page Structure) ---")
with open(exam_pdf, "rb") as f:
    reader = PyPDF2.PdfReader(f)
    for i in range(min(2, len(reader.pages))):
        print(f"Page {i+1}")
        text = reader.pages[i].extract_text()
        print(text[:1000] + "\n...\n")
