import re
from datetime import datetime

from ..models import Statement, Transaction
from ..pdf_text import page_lines, parse_amount
from .common import close, join_description, money

ACCOUNT = "Ryt"

_DATE = r"\d{1,2} [A-Za-z]{3} \d{4}"
# date, description, signed amount, balance
_TXN = re.compile(rf"^({_DATE}) (.+?) ([+-][\d,]+\.\d{{2}}) ([\d,]+\.\d{{2}})$")
_OPENING = re.compile(rf"^{_DATE} Opening balance ([\d,]+\.\d{{2}})$")
_CLOSING = re.compile(r"^([\d,]+\.\d{2})$")  # the line after "Closing balance (MYR)"
_CARD = re.compile(r"^Card ••\d{4}\s*(?:([A-Z]{3}) ([\d,]+\.\d{2}))?$")  # card, optional foreign amount
_REF = re.compile(rf"^Ref\. ID: \S+(?: \| Transaction date: ({_DATE}))?(?: Fee MYR ([\d,]+\.\d{{2}}))?$")
_SKIPPED = re.compile(r"^(Daily interest payout|From Ryt Pocket)$", re.I)
_TABLE_END = ("YTL Digital Bank", "Closing balance", "END OF STATEMENT")


def matches(first_page: str) -> bool:
    return "YTL Digital Bank" in first_page and "Savings Account Statement" in first_page


def _date(text: str):
    return datetime.strptime(text, "%d %b %Y").date()


def parse(path, password="") -> Statement:
    st = Statement("Ryt Savings", ACCOUNT)

    opening = closing = None
    txns = []  # dicts: date, value, balance, lines, foreign, fee
    expect_closing = False
    for lines in page_lines(path, password):
        in_table = False
        for line in lines:
            line = line.strip()
            if expect_closing and (m := _CLOSING.match(line)):
                closing = parse_amount(m.group(1))
                expect_closing = False
                continue
            if line.startswith("Closing balance"):
                expect_closing = True
            if line.startswith("Amaun Baki"):
                in_table = True
                continue
            if not in_table:
                continue
            if line.startswith(_TABLE_END):
                in_table = False
                continue
            if m := _OPENING.match(line):
                opening = parse_amount(m.group(1))
            elif m := _TXN.match(line):
                date, desc, amount, balance = m.groups()
                txns.append({"date": _date(date), "value": parse_amount(amount) * (1 if amount[0] == "+" else -1),
                             "balance": parse_amount(balance), "lines": [desc], "foreign": "", "fee": 0.0})
            elif txns:
                t = txns[-1]
                if m := _CARD.match(line):
                    if m.group(1):
                        t["foreign"] = f"{m.group(2)} {m.group(1)}"
                elif m := _REF.match(line):
                    if m.group(1):
                        t["date"] = _date(m.group(1))  # card purchases: use the purchase date
                    if m.group(2):
                        t["fee"] = parse_amount(m.group(2))
                else:
                    t["lines"].append(line)

    if opening is None:
        raise ValueError("Could not find the opening balance.")

    running = opening
    bad_rows = 0
    for t in txns:
        running += t["value"]
        if not close(running, t["balance"]):
            bad_rows += 1
            running = t["balance"]
        merchant = t["lines"][0]
        if _SKIPPED.match(merchant):
            continue
        extras = [x for x in (t["foreign"], f"fee {t['fee']:.2f} MYR" if t["fee"] else "") if x]
        description = join_description(t["lines"]) + (f" ({', '.join(extras)})" if extras else "")
        key = re.sub(r"^(To|From) ", "", merchant)
        st.transactions.append(Transaction(t["date"], ACCOUNT, round(t["value"], 2), description, key=key))

    if closing is None:
        st.check = "Could not find the closing balance."
    else:
        total = opening + sum(t["value"] for t in txns)
        st.check_ok = close(total, closing) and bad_rows == 0
        st.check = (
            f"Opening {money(opening)} + transactions = {money(total)}; "
            f"closing balance {money(closing)} (Main Account only)."
        )
        if bad_rows:
            st.check += f" {bad_rows} row(s) did not match the running balance."
    return st
