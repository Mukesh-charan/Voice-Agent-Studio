with open('../references.bib', 'r', encoding='utf-8') as f:
    text = f.read()

print("Contains hartmann2010:", "hartmann2010" in text)
print("Contains glover2019:", "glover2019" in text)
print("Contains farhi2014:", "farhi2014" in text)
