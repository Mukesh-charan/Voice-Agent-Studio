with open('../journal.tex.bak', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

for i in range(855, 930):
    if "Table" in lines[i] or "tab:latency" in lines[i]:
        for j in range(max(0, i-5), min(len(lines), i+30)):
            print(f"L{j+1}: {repr(lines[j])}")
        break
