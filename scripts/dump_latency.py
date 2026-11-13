with open('../journal.tex', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

def print_range(start, end):
    for i in range(start-1, min(end, len(lines))):
        print(f"L{i+1}: {lines[i]}")

print("=== LATENCY BOX & SUBSYSTEM DYNAMICS ===")
print_range(860, 922)
