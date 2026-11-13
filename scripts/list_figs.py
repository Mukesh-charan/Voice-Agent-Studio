with open('../journal.tex', 'r', encoding='utf-8') as f:
    text = f.read()

lines = text.splitlines()

for i, line in enumerate(lines):
    if '\\begin{figure' in line:
        fig_start = i + 1
        caption = ""
        label = ""
        for j in range(i, min(i+100, len(lines))):
            if '\\caption{' in lines[j]:
                caption = lines[j].strip()
            if '\\label{' in lines[j]:
                label = lines[j].strip()
            if '\\end{figure' in lines[j]:
                fig_end = j + 1
                break
        print(f"L{fig_start}-{fig_end}: {label} | {caption[:70]}")
