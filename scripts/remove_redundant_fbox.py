with open('../journal.tex', 'r', encoding='utf-8') as f:
    content = f.read()

old_badge_line = r"""  \node[anchor=south west, font=\tiny\bfseries\color{eaSlate}] at (0.2, -1.55) {\fbox{Docker Appliance: Multi-Process Microservice ($\approx 2.1$\,GB, CUDA/Alpine)}};"""

assert old_badge_line in content, "Error: old_badge_line not found"
content = content.replace(old_badge_line, "", 1)

with open('../journal.tex', 'w', encoding='utf-8') as f:
    f.write(content)

print("Removed redundant bottom fbox from Figure 1.")
