import pypdf
import os

pdf_path = "../journal.pdf"
if os.path.exists(pdf_path):
    reader = pypdf.PdfReader(pdf_path)
    print(f"Total PDF pages: {len(reader.pages)}")
    print(f"PDF size: {os.path.getsize(pdf_path):,} bytes")
else:
    print("PDF not found!")
