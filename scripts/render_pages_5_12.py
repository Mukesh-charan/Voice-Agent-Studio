import fitz

doc = fitz.open("../journal.pdf")
for pno in [4, 11, 12]:
    page = doc[pno]
    pix = page.get_pixmap(dpi=200)
    pix.save(f"render_page_{pno+1}.png")
    print(f"Saved render_page_{pno+1}.png")
