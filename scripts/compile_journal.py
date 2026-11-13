import subprocess
import os

os.chdir("..")
print("Working dir:", os.getcwd())

cmd1 = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "journal.tex"]
cmd2 = ["bibtex", "journal"]
cmd3 = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "journal.tex"]
cmd4 = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "journal.tex"]

print("Pass 1: pdflatex...")
r1 = subprocess.run(cmd1, capture_output=True, text=True)
print("Pass 1 exit:", r1.returncode)
if r1.returncode != 0:
    print(r1.stdout[-2000:])
    exit(1)

print("Pass 2: bibtex...")
r2 = subprocess.run(cmd2, capture_output=True, text=True)
print("Bibtex exit:", r2.returncode)
if r2.returncode != 0:
    print(r2.stdout[-1000:])

print("Pass 3: pdflatex...")
r3 = subprocess.run(cmd3, capture_output=True, text=True)
print("Pass 3 exit:", r3.returncode)

print("Pass 4: pdflatex...")
r4 = subprocess.run(cmd4, capture_output=True, text=True)
print("Pass 4 exit:", r4.returncode)
if r4.returncode == 0:
    print("SUCCESS! journal.pdf compiled cleanly.")
else:
    print(r4.stdout[-2000:])
