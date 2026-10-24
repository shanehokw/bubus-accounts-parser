import re
from datetime import datetime

from ..models import Statement, Transaction
from ..pdf_text import page_lines, parse_amount
from .common import close, infer_year, money

ACCOUNT = "Maybank"

_STATEMENT_DATE = re.compile(r"(\d{2} [A-Z]{3} \d{2}) \d{2} [A-Z]{3} \d{2}")
# posting date, transaction date, description, amount, optional CR
_TXN = re.compile(r"^(\d{2})/(\d{2}) (\d{2})/(\d{2}) (.+?) ([\d,]+\.\d{2})(CR)?$")
_PREVIOUS = re.compile(r"YOUR PREVIOUS STATEMENT BALANCE ([\d,]+\.\d{2})(CR)?")
_SUBTOTAL = re.compile(r"SUB TOTAL/JUMLAH ([\d,]+\.\d{2})(CR)?")
_SKIP = re.compile(r"CASH ?REBATE|CASHBACK", re.I)
_INSTALMENT = re.compile(r"\s*:\d{3}/\d{3}$")


def matches(first_page: str) -> bool:
    return "Malayan Banking" in first_page and "CREDIT CARD" in first_page


def _signed(amount: str, cr: str) -> float:
    """Card balances: amount owed is negative, credit is positive."""
    return parse_amount(amount) * (1 if cr else -1)


def parse(path, password="") -> Statement:
    st = Statement("Maybank Credit Card", ACCOUNT)
    lines = [l.strip() for page in page_lines(path, password) for l in page]

    statement_date = None
    for line in lines:
        if m := _STATEMENT_DATE.search(line):
            statement_date = datetime.strptime(m.group(1), "%d %b %y").date()
            break
    if statement_date is None:
        raise ValueError("Could not find the statement date.")

    previous = subtotal = 0.0
    all_amounts = 0.0
    for line in lines:
        if m := _PREVIOUS.search(line):
            previous += _signed(m.group(1), m.group(2))
        elif m := _SUBTOTAL.search(line):
            subtotal += _signed(m.group(1), m.group(2))
        elif m := _TXN.match(line):
            _, _, day, month, desc, amount, cr = m.groups()
            value = _signed(amount, cr)
            all_amounts += value
            if _SKIP.search(desc):
                continue
            d = infer_year(int(day), int(month), statement_date)
            key = _INSTALMENT.sub("", desc).lstrip("*").strip()
            st.transactions.append(Transaction(d, ACCOUNT, value, desc, key=key))

    total = previous + all_amounts
    st.check_ok = close(total, subtotal)
    st.check = (
        f"Previous balance {money(previous)} + transactions = {money(total)}; "
        f"statement balance {money(subtotal)} (negative = owed)."
    )
    return st
