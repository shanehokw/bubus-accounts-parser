import re
from datetime import date

from ..models import Statement, Transaction
from ..pdf_text import parse_amount
from .common import clean_line, close, is_noise, join_description, money, month_number

ACCOUNT = "HSBC"

# Day is always two digits; the month's 3rd letter may come back from OCR as 1 or | (Jul).
_DATE = re.compile(r"^(\d{2})([A-Za-z0]{2}[A-Za-z0|1])(\d{4})\s*(.*)$")
_AMOUNT = re.compile(r"^\d[\d,.]*\.\d{2}$")
_STATEMENT_DATE = re.compile(r"Statement Date\s+(\d{1,2})([A-Za-z0]{3})(\d{4})")
_ACCOUNT_NUMBER = re.compile(r"^\d{8,}$")
_TABLE_END = ("BALANCE CARRIED FORWARD", "CLOSING BALANCE", "END OF STATEMENT")
_AMOUNT_COLUMN_X = 330  # amounts sit right of the description column (page is 595 wide)


def matches(first_page: str) -> bool:
    return "HSBC" in first_page and "PERSONAL FINANCIAL UPDATE" in first_page.upper()


def _to_date(day, month, year) -> date:
    return date(int(year), month_number(month), int(day))


def parse(rows) -> Statement:
    st = Statement("HSBC Savings", ACCOUNT)

    opening = closing = None
    current_date = None
    pending = []  # description lines waiting for their amount row
    txns = []  # (date, amount, balance, lines)
    in_table = False
    page = -1

    for row in rows:
        if row.page != page:
            page, in_table = row.page, False
        text = row.text.strip()

        if "Transaction Details" in text and ("Deposits" in text or "Withdrawals" in text):
            in_table = True
            continue
        if not in_table:
            continue

        amounts = [s for s in row.segments if s.x0 > _AMOUNT_COLUMN_X and _AMOUNT.match(s.text)]
        words = [s.text for s in row.segments if s.x0 <= _AMOUNT_COLUMN_X]

        if words and (m := _DATE.match(words[0])):
            current_date = _to_date(*m.groups()[:3])
            words = ([m.group(4)] if m.group(4) else []) + words[1:]
        line = " ".join(words).strip()

        if "BALANCE BROUGHT FORWARD" in line:
            if opening is None and amounts:
                opening = parse_amount(amounts[-1].text)
            continue
        if any(end in line for end in _TABLE_END):
            if line.startswith("CLOSING BALANCE") and amounts:
                closing = parse_amount(amounts[-1].text)
            in_table = False
            continue

        if line:
            pending.append(line)
        if len(amounts) >= 2:
            amount, balance = parse_amount(amounts[-2].text), parse_amount(amounts[-1].text)
            txns.append((current_date, amount, balance, pending))
            pending = []

    if opening is None:
        raise ValueError("Could not find the balance brought forward.")

    # The running balance tells whether each amount was a deposit or a withdrawal.
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
        st.transactions.append(Transaction(d, ACCOUNT, round(value, 2), join_description(lines),
                                           key=_counterparty(lines)))

    if unclear:
        st.warnings.append(
            f"{unclear} amount(s) did not match the running balance; their value was taken "
            "from the change in balance. Check them against the PDF."
        )
    if closing is None:
        st.check = "Could not find the closing balance."
    else:
        total = opening + sum(t.value for t in st.transactions)
        st.check_ok = close(total, closing) and not unclear
        st.check = (
            f"Brought forward {money(opening)} + transactions = {money(total)}; "
            f"closing balance {money(closing)}."
        )
    return st


def _counterparty(lines: list) -> str:
    """Incoming transfers name the sender after 'TRANSFER FROM'; outgoing ones put the
    recipient just above their account number."""
    lines = [clean_line(l) for l in lines]
    if lines and lines[0].upper().startswith("TRANSFER FROM") and len(lines) > 1:
        return lines[1]
    for i, line in enumerate(lines):
        if _ACCOUNT_NUMBER.match(line.replace(" ", "")) and i > 0 and not is_noise(lines[i - 1]):
            return lines[i - 1]
    meaningful = [l for l in lines if not is_noise(l)]
    return meaningful[0] if meaningful else ""
