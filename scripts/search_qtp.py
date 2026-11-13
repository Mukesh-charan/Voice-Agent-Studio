with open('../journal.tex', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

for i, line in enumerate(lines):
    if any(k in line.lower() for k in ['qtp', 'task parallel', 'quantum task', 'scheduler']):
        print(f"L{i+1}: {line.strip()[:100]}")
