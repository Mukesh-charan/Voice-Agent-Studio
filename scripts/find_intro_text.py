with open('../journal.tex.bak', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

for i, line in enumerate(lines):
    if "To overcome these compounding challenges" in line or "primary contributions" in line:
        for j in range(max(0, i-5), min(len(lines), i+25)):
            print(f"L{j+1}: {repr(lines[j])}")
        break
