with open('../journal.tex', 'r', encoding='utf-8') as f:
    content = f.read()

old_badge = r"""\node[anchor=south east, font=\tiny\bfseries\color{eaSlate}] at (17.4, -1.6) {\fbox{Docker Appliance: Multi-Process Microservice ($\approx 2.1$\,GB, CUDA/Alpine)}};"""
new_badge = r"""\node[anchor=south west, font=\tiny\bfseries\color{eaSlate}] at (0.2, -1.55) {\fbox{Docker Appliance: Multi-Process Microservice ($\approx 2.1$\,GB, CUDA/Alpine)}};"""

assert old_badge in content, "Error: old_badge not found"
content = content.replace(old_badge, new_badge, 1)

with open('../journal.tex', 'w', encoding='utf-8') as f:
    f.write(content)

print("Moved Docker badge to bottom-left, completely clearing bottom-right.")
