import io
import zipfile
import sqlite3
from starlette.testclient import TestClient
from server import app

def test_kb_file_uploads():
    conn = sqlite3.connect("agents.db")
    token_row = conn.execute("SELECT token FROM sessions WHERE user_id = 1 ORDER BY rowid DESC LIMIT 1").fetchone()
    token = token_row[0] if token_row else ""
    client = TestClient(app, cookies={"session": token})

    # 1. Test TXT file upload
    txt_data = b"Our clinic opens at 8 AM and closes at 6 PM Monday to Friday."
    r_txt = client.post("/api/agents/1/documents", files={"file": ("hours.txt", txt_data)})
    assert r_txt.status_code == 200, r_txt.text
    assert r_txt.json()["chunks"] >= 1

    # 2. Test DOCX file upload
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body><w:p><w:r><w:t>Deluxe suite pricing is 250 USD.</w:t></w:r></w:p></w:body></w:document>")
    r_docx = client.post("/api/agents/1/documents", files={"file": ("rates.docx", buf.getvalue())})
    assert r_docx.status_code == 200, r_docx.text
    assert r_docx.json()["chunks"] >= 1

    # 3. Test unowned/seeded agent auto-claim and upload
    r_seed = client.post("/api/agents/2/documents", files={"file": ("seed.txt", b"Seeded agent knowledge document.")})
    assert r_seed.status_code == 200, r_seed.text
