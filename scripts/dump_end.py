with open('../journal.tex', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

for i in range(1117, len(lines)):
    print(f"L{i+1}: {lines[i]}")
