try:
    import fitz
    print("fitz available")
    doc = fitz.open("../journal.pdf")
    print("Total pages in fitz:", len(doc))
    # render page 2 (where Fig 1 is) and page 10 (where Fig 9/10 is)
    for pno in [0, 1, 9, 10]:
        if pno < len(doc):
            page = doc[pno]
            pix = page.get_pixmap(dpi=150)
            pix.save(f"page_{pno+1}.png")
            print(f"Saved page_{pno+1}.png")
except Exception as e:
    print("fitz error:", e)
