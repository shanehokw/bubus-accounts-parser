import re
from datetime import datetime

from ..models import Statement, Transaction
from ..pdf_text import page_lines, parse_amount
from .common import clean_line, close, is_noise, join_description, money

ACCOUNT = "Maybank"

_TXN = re.compile(r"^(\d{2}/\d{2}/\d{2})\s+(.*?)\s*([\d,]+\.\d{2})([+-])\s+([\d,]+\.\d{2})$")
_AMOUNT_AFTER = r"\s*:?\s*([\d,]+\.\d{2})"


def matches(first_page: str) -> bool:
    return "Malayan Banking" in first_page and "ACCOUNT TRANSACTIONS" in first_page


def parse(path, password="") -> Statement:
    st = Statement("Maybank Savings", ACCOUNT)
    pages = page_lines(path, password)

    opening = ending = None
    txns = []  # (date, signed amount, balance, [description lines])

    for lines in pages:
        in_table = False
        for line in lines:
            line = line.strip()
            if line.startswith("ENTRY DATE"):
                in_table = True
                continue
            if not in_table:
                continue
            if line.startswith("Perhation") or line.startswith("TOTAL "):
                in_table = False
                continue
            if m := re.match(r"BEGINNING BALANCE" + _AMOUNT_AFTER, line):
                opening = parse_amount(m.group(1))
            elif m := re.match(r"ENDING BALANCE" + _AMOUNT_AFTER, line):
                ending = parse_amount(m.group(1))
            elif m := _TXN.match(line):
                d = datetime.strptime(m.group(1), "%d/%m/%y").date()
                amount = parse_amount(m.group(3)) * (1 if m.group(4) == "+" else -1)
                txns.append((d, amount, parse_amount(m.group(5)), [m.group(2)]))
            elif txns:
                txns[-1][3].append(line)

    if opening is None:
        st.warnings.append("Could not find the beginning balance.")

    running = opening or 0.0
    bad_rows = 0
    for d, amount, balance, lines in txns:
        running += amount
        if not close(running, balance):
            bad_rows += 1
            running = balance
        # The counterparty is usually the line under the transaction type.
        counterparty = next(
            (clean_line(l) for l in lines[1:] if not is_noise(clean_line(l))), clean_line(lines[0]))
        st.transactions.append(
            Transaction(d, ACCOUNT, amount, join_description(lines), key=counterparty)
        )

    _check(st, opening, ending, txns, bad_rows)
    return st


def _check(st, opening, ending, txns, bad_rows):
    if opening is None or ending is None:
        st.check = "Could not find the beginning or ending balance."
        return
    total = opening + sum(t[1] for t in txns)
    st.check_ok = close(total, ending) and bad_rows == 0
    st.check = (
        f"Beginning {money(opening)} + transactions = {money(total)}; "
        f"statement ending balance {money(ending)}."
    )
    if bad_rows:
        st.check += f" {bad_rows} row(s) did not match the running balance."
