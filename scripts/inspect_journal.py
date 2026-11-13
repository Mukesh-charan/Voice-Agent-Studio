import re

with open('../journal.tex', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()
print(f"Total lines: {len(lines)}")

# Find sections and figures
for i, line in enumerate(lines):
    if line.strip().startswith('\\section') or line.strip().startswith('\\subsection') or line.strip().startswith('\\subsubsection'):
        print(f"L{i+1}: {line.strip()}")
    elif '\\begin{figure' in line:
        print(f"L{i+1}: FIGURE BEGIN -> {line.strip()}")
    elif '\\caption{' in line:
        print(f"L{i+1}:   {line.strip()[:80]}")
