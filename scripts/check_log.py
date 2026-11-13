with open('../journal.log', 'r', encoding='utf-8', errors='ignore') as f:
    log = f.read()

warnings = [line for line in log.splitlines() if 'Warning:' in line or 'Error' in line]
print(f"Total warning/error lines: {len(warnings)}")
for w in warnings[:15]:
    print("  ", w)
