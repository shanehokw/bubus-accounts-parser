import re
from datetime import datetime

from ..models import Statement, Transaction
from ..pdf_text import page_lines, parse_amount
from .common import clean_line, close, infer_year, is_noise, join_description, money, month_number

ACCOUNT = "RHB"

_PERIOD = re.compile(r"Statement Period / Tempoh Penyata : \d{1,2} \w{3} \d{2} \S (\d{1,2} \w{3} \d{2})")
# date, description (ending in a serial number like 001), amount, balance ('-' = overdrawn)
_TXN = re.compile(r"^(\d{1,2}) ([A-Za-z]{3}) (.+?)\s+([\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2}-?)$")
_SERIAL = re.compile(r"\s+\d{3}$")
_BALANCE_LINE = re.compile(r"^\d{1,2} [A-Za-z]{3} ([BC])/F BALANCE (-?[\d,]+\.\d{2}-?)$")
# Payment-type lines that name no one, so they make poor category rules.
_GENERIC = re.compile(r"^(QR \w+ Payment|IBG TRANSACTION|Payment)$", re.I)


def matches(first_page: str) -> bool:
    # Spaces removed: with the default tolerance the header reads "RHBBankBerhad".
    squashed = "".join(first_page.split()).upper()
    return "RHBBANKBERHAD" in squashed and "ACCOUNTSTATEMENT/PENYATAAKAUN" in squashed


def _balance(text: str) -> float:
    return -parse_amount(text) if "-" in text else parse_amount(text)


def parse(path, password="") -> Statement:
    st = Statement("RHB Savings", ACCOUNT)
    # The letters in RHB's PDFs sit close together; a tighter tolerance keeps the spaces.
    pages = page_lines(path, password, x_tolerance=1.5)

    end_date = None
    for line in pages[0]:
        if m := _PERIOD.search(line):
            end_date = datetime.strptime(m.group(1), "%d %b %y").date()
            break
    if end_date is None:
        raise ValueError("Could not find the statement period.")

    opening = closing = None
    txns = []  # (date, amount, balance, [description lines])
    for lines in pages:
        in_table = False
        for line in lines:
            line = line.strip()
            if line.startswith("Tarikh Diskripsi"):
                in_table = True
                continue
            if not in_table:
                continue
            if line.startswith(("Member of PIDM", "Total Count")):
                in_table = False
                continue
            if m := _BALANCE_LINE.match(line):
                if m.group(1) == "B":
                    opening = _balance(m.group(2))
                else:
                    closing = _balance(m.group(2))
            elif m := _TXN.match(line):
                day, month, desc, amount, balance = m.groups()
                d = infer_year(int(day), month_number(month), end_date)
                txns.append((d, parse_amount(amount), _balance(balance), [_SERIAL.sub("", desc)]))
            elif txns:
                txns[-1][3].append(line)  # also picks up lines carried over to the next page

    if opening is None:
        raise ValueError("Could not find the B/F balance.")

    # Debit and credit share a line, so the running balance tells which one each amount is.
    previous = opening
    unclear = 0
    for d, amount, balance, lines in txns:
        if close(previous + amount, balance):
            value = amount
        elif close(previous - amount, balance):
            value = -amount
        else:
            value = balance - previous
            unclear += 1
        previous = balance
        counterparty = next(
            (clean_line(l) for l in lines[1:]
             if not is_noise(clean_line(l)) and not _GENERIC.match(clean_line(l))),
            clean_line(lines[0]))
        st.transactions.append(
            Transaction(d, ACCOUNT, round(value, 2), join_description(lines), key=counterparty))

    if unclear:
        st.warnings.append(
            f"{unclear} amount(s) did not match the running balance; their value was taken "
            "from the change in balance. Check them against the PDF."
        )
    if closing is None:
        st.check = "Could not find the C/F balance."
    else:
        total = opening + sum(t.value for t in st.transactions)
        st.check_ok = close(total, closing) and not unclear
        st.check = (
            f"B/F balance {money(opening)} + transactions = {money(total)}; "
            f"C/F balance {money(closing)}."
        )
    return st
