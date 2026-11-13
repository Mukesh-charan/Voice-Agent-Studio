with open('../journal.tex.bak', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

for i, line in enumerate(lines):
    if "Edge Runtime Voice Pipeline" in line:
        for j in range(max(0, i-15), min(len(lines), i+5)):
            print(f"L{j+1}: {repr(lines[j])}")
        break
