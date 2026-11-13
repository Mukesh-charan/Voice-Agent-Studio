import fitz

doc = fitz.open("../journal.pdf")
for i, page in enumerate(doc):
    text = page.get_text()
    if "Figure 1:" in text:
        print(f"Figure 1 on Page {i+1}")
    if "Figure" in text and "QTP" in text:
        print(f"Figure with QTP on Page {i+1}")
    if "Quantum Task Parallelizer" in text:
        print(f"QTP mentioned on Page {i+1}")
