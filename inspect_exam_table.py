import pdfplumber
import pprint

exam_pdf = "Final DateSheet Sessional 2 Spring-2026.pdf"
with pdfplumber.open(exam_pdf) as pdf:
    for i, page in enumerate(pdf.pages[:1]):
        tables = page.extract_tables()
        print("Num tables:", len(tables))
        if tables:
            pprint.pprint(tables[0][:5]) # print first 5 rows
