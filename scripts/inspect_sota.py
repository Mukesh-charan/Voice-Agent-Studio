with open('../journal.tex', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

# Check Table SOTA (tab:sota)
for i, line in enumerate(lines):
    if 'tab:sota' in line:
        print(f"tab:sota around line {i+1}")
        for j in range(max(0, i-15), min(len(lines), i+30)):
            print(f"L{j+1}: {lines[j]}")
        break
