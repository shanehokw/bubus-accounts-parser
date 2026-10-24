import re
from datetime import date

from ..models import Statement, Transaction
from ..pdf_text import parse_amount
from .common import close, infer_year, money, month_number

ACCOUNT = "HSBC"

_AMOUNT = r"(\d[\d,.]*\.\d{2})\s?(CR)?"
_DATE = r"(\d{1,2}) ?([A-Z0]{3})"
# posting date, transaction date, description, amount
_TXN = re.compile(rf"^{_DATE} {_DATE} (.+?) {_AMOUNT}$")
_FOREIGN = re.compile(r"^[\d,.]+\.\d{2} [A-Z]{3}$")
_STATEMENT_DATE = re.compile(r"Statement Date (\d{1,2}) ([A-Za-z0]{3})[a-z]* (\d{4})")
_PREVIOUS = re.compile(rf"Your Previous Statement Balance {_AMOUNT}", re.I)
_BALANCE = re.compile(rf"Your statement balance {_AMOUNT}", re.I)
_SKIP = re.compile(r"CASH ?REBATE|CASHBACK", re.I)
_DATE_OR_AMOUNT = re.compile(rf"^({_DATE}( {_DATE})?|{_AMOUNT})$")


def matches(first_page: str) -> bool:
    return "HSBC" in first_page and "Account Statement" in first_page


def _signed(amount: str, cr: str) -> float:
    return parse_amount(amount) * (1 if cr else -1)


def parse(rows) -> Statement:
    st = Statement("HSBC Credit Card", ACCOUNT)

    statement_date = None
    for row in rows:
        if m := _STATEMENT_DATE.search(row.text):
            statement_date = date(int(m.group(3)), month_number(m.group(2)), int(m.group(1)))
            break
    if statement_date is None:
        raise ValueError("Could not find the statement date.")

    previous = balance = None
    all_amounts = 0.0
    last = None  # last transaction added, for foreign-currency lines that follow it
    for row in rows:
        text = row.text.strip()
        if m := _PREVIOUS.search(text):
            previous = _signed(m.group(1), m.group(2))
        elif m := _BALANCE.search(text):
            balance = _signed(m.group(1), m.group(2))
        elif m := _TXN.match(text):
            _, _, day, month, desc, amount, cr = m.groups()
            value = _signed(amount, cr)
            all_amounts += value
            last = None
            if _SKIP.search(desc):
                continue
            d = infer_year(int(day), month_number(month), statement_date)
            # The merchant is the first text piece after the two dates; the location follows.
            pieces = [s.text for s in row.segments if not _DATE_OR_AMOUNT.match(s.text)]
            key = pieces[0] if len(pieces) > 1 and pieces[0] in desc else desc
            last = Transaction(d, ACCOUNT, value, re.sub(r"\s+", " ", desc), key=key)
            st.transactions.append(last)
        elif last and _FOREIGN.match(text):
            last.description += f" ({text})"
            last = None
        else:
            last = None

    if previous is None or balance is None:
        st.check = "Could not find the previous or current statement balance."
    else:
        total = previous + all_amounts
        st.check_ok = close(total, balance)
        st.check = (
            f"Previous balance {money(previous)} + transactions = {money(total)}; "
            f"statement balance {money(balance)} (negative = owed)."
        )
    return st
