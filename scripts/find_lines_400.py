with open('../journal.tex.bak', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

for i in range(400, 440):
    print(f"L{i+1}: {repr(lines[i])}")
