"""Parses every PDF in a folder and prints what was found. For checking parser changes.

Usage: .venv/bin/python check_samples.py ["Statement Samples"] [--rows]
"""

import sys
from pathlib import Path

from statement_parser import parse_statement

folder = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), "Statement Samples"))
show_rows = "--rows" in sys.argv

for pdf in sorted(folder.glob("*.pdf")):
    print(f"\n=== {pdf.name}")
    try:
        st = parse_statement(pdf)
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        continue
    total = sum(t.value for t in st.transactions)
    print(f"  {st.kind} -> ACCOUNT {st.account}: {len(st.transactions)} rows, net {total:,.2f}")
    print(f"  Check {'OK' if st.check_ok else 'FAILED'}: {st.check}")
    for w in st.warnings:
        print(f"  Warning: {w}")
    if show_rows:
        for t in st.transactions:
            print(f"    {t.date:%d/%m/%Y} {t.value:>10,.2f}  {t.description}  [key: {t.key}]")
