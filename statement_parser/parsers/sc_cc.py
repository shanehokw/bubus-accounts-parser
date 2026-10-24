import re
from datetime import datetime

from ..models import Statement, Transaction
from ..pdf_text import page_lines, parse_amount
from .common import close, infer_year, is_noise, money, month_number

ACCOUNT = "SC CC"

_STATEMENT_DATE = re.compile(r"Statement Date / Tarikh Penyata : (\d{1,2} \w{3} \d{4})")
# posting date, transaction date, then description ... Txn Ref ... amount
_TXN = re.compile(r"^(\d{1,2}) ([A-Za-z]{3}) (\d{1,2}) ([A-Za-z]{3}) (.*?)([\d,]+\.\d{2})(CR)?$")
_FOREIGN = re.compile(r"\b([A-Z]{3}) ([\d,]+\.\d{2})\s*$")  # currency and amount before the RM amount
_PREVIOUS = re.compile(r"^PREVIOUS STATEMENT ([\d,]+\.\d{2})(CR)?$")
_NEW_BALANCE = re.compile(r"^New BALANCE ([\d,]+\.\d{2})(CR)?$", re.I)
_SKIP = re.compile(r"CASH ?REBATE|CASHBACK", re.I)
_END = ("A Standard Chartered Group Company", "New BALANCE")


def matches(first_page: str) -> bool:
    return "Standard Chartered" in first_page and "Credit Card Statement" in first_page


def _signed(amount: str, cr: str) -> float:
    """Card balances: amount owed is negative, credit is positive."""
    return parse_amount(amount) * (1 if cr else -1)


def _words(line: str) -> list:
    """A description line without its reference numbers."""
    line = re.sub(r"Txn Ref:\s*\S*", "", line)
    return [w for w in line.split() if not is_noise(w)]


def parse(path, password="") -> Statement:
    st = Statement("SC Credit Card", ACCOUNT)
    lines = [l.strip() for page in page_lines(path, password) for l in page]

    statement_date = None
    for line in lines:
        if m := _STATEMENT_DATE.search(line):
            statement_date = datetime.strptime(m.group(1), "%d %b %Y").date()
            break
    if statement_date is None:
        raise ValueError("Could not find the statement date.")

    previous = new_balance = None
    txns = []  # (date, value, merchant, foreign, [continuation lines])
    current = None
    for line in lines:
        if m := _PREVIOUS.match(line):
            previous = _signed(m.group(1), m.group(2))
        elif m := _NEW_BALANCE.match(line):
            new_balance = _signed(m.group(1), m.group(2))
        if line.startswith(_END):
            current = None
        elif m := _TXN.match(line):
            _, _, day, month, rest, amount, cr = m.groups()
            merchant, _, after_ref = rest.partition("Txn Ref")
            foreign = _FOREIGN.search(after_ref)
            d = infer_year(int(day), month_number(month), statement_date)
            current = (d, _signed(amount, cr), merchant.strip(),
                       f"{foreign.group(2)} {foreign.group(1)}" if foreign else "", [])
            txns.append(current)
        elif current is not None:
            current[4].append(line)

    for d, value, merchant, foreign, more in txns:
        words = _words(merchant) + [w for l in more for w in _words(l)]
        description = " ".join(words) + (f" ({foreign})" if foreign else "")
        if _SKIP.search(description):
            continue
        st.transactions.append(Transaction(d, ACCOUNT, value, description, key=merchant))

    if previous is None or new_balance is None:
        st.check = "Could not find the previous or new balance."
    else:
        total = previous + sum(t[1] for t in txns)
        st.check_ok = close(total, new_balance)
        st.check = (
            f"Previous balance {money(previous)} + transactions = {money(total)}; "
            f"new balance {money(new_balance)} (negative = owed)."
        )
    return st
