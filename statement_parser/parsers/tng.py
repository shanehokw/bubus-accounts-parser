import re
from datetime import datetime

from ..models import Statement, Transaction
from ..pdf_text import parse_amount
from .common import close, money

ACCOUNT = "TNG"

_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
# The reference number often runs into the end of the transaction type ("Receive from Wallet20250101111").
_TRAILING_REF = re.compile(r"(MMF)?\d{6,}$")
_LONG_NUMBER = re.compile(r"\d{15,}")  # reference numbers that spill into the description

# Transaction types (spaces removed, upper case) → direction. Matched by prefix, longest first.
SKIPPED = ["RELOAD", "GO+DAILYEARNINGS"]
MONEY_IN = [
    "RELOAD", "RECEIVEFROMWALLET", "DUITNOW_RECEIVEFROM", "MONEYPACKETRECEIVED", "MONEY_PACKET_REFUND",
    "CASHBACK", "PAYMENTCANCELLED", "TRANSIT_PASS_REFUND", "GO+CASHIN", "REFUND",
]
MONEY_OUT = [
    "PAYMENT", "PAYDIRECTPAYMENT", "DUITNOWQR", "TRANSFERTOWALLET", "DUITNOW_TRANSFERTO",
    "TRANSIT_PASS", "CARDISSUANCE_PAYMENT", "EWALLETCASHOUT", "MONEYPACKET",
]
# GO+ rows show the GO+ balance rather than the wallet balance.
GO_PLUS = ["GO+CASHIN", "GO+DAILYEARNINGS"]

NICE_TYPES = {
    "DUITNOW_TRANSFERTO": "DuitNow Transfer",
    "DUITNOW_RECEIVEFROM": "DuitNow Receive",
    "TRANSIT_PASS": "Transit Pass",
    "TRANSIT_PASS_REFUND": "Transit Pass Refund",
    "CARDISSUANCE_PAYMENT": "Card Payment",
    "MONEY_PACKET_REFUND": "Money Packet Refund",
}


def matches(first_page: str) -> bool:
    return "TNG WALLET TRANSACTION HISTORY" in first_page


def _match(type_key: str, prefixes: list) -> str:
    hits = [p for p in prefixes if type_key.startswith(p)]
    return max(hits, key=len) if hits else ""


def parse(rows) -> Statement:
    st = Statement("TNG eWallet", ACCOUNT)

    columns = None  # header x positions
    txns = []
    current = None
    for row in rows:
        text = row.text
        if "Status" in text and "Reference" in text and "Description" in text:
            if columns is None:
                columns = {s.text: s.x0 for s in row.segments}
            continue  # the header repeats on some pages
        if columns is None:
            continue
        if text.startswith("*This is a system generated"):
            current = None
            continue
        first = row.segments[0]
        if _DATE.match(first.text) and first.x0 < columns["Status"]:
            current = {"date": first.text, "status": "", "type": [], "desc": [], "amount": "", "balance": ""}
            txns.append(current)
        if current is None:
            continue
        for s in row.segments:
            if s.x0 < columns["Status"]:
                continue
            elif s.x0 < columns["Transaction"]:
                current["status"] += s.text
            elif s.x0 < columns["Reference"]:
                current["type"].append(s.text)
            elif s.x0 < columns["Description"]:
                pass  # reference number
            elif s.x0 < columns["Details"]:
                current["desc"].append(s.text)
            elif s.x0 < columns["Amount"] - 30:
                pass  # details: timestamps and reference numbers
            elif s.x0 < columns["Wallet"] - 10:
                current["amount"] += s.text
            else:
                current["balance"] += s.text

    if columns is None:
        raise ValueError("Could not find the transaction table.")

    wallet = None  # running wallet balance, for checking
    mismatches = []  # descriptions of rows where the wallet balance did not follow
    unknown = set()
    for t in txns:
        type_text = " ".join(_TRAILING_REF.sub("", p) for p in t["type"]).strip()
        type_key = type_text.replace(" ", "").upper()
        if not t["amount"] or t["status"].upper() == "FAILED":
            continue
        amount = parse_amount(t["amount"])
        d = datetime.strptime(t["date"], "%d/%m/%Y").date()

        inn, out = _match(type_key, MONEY_IN), _match(type_key, MONEY_OUT)
        if not inn and not out and not _match(type_key, SKIPPED):
            unknown.add(type_text)
        value = amount if len(inn) > len(out) else -amount

        balance = parse_amount(t["balance"]) if re.search(r"\d", t["balance"]) else None
        if not _match(type_key, GO_PLUS):
            if wallet is None and balance is not None:
                wallet = balance - value
            if wallet is not None:
                wallet += value
                if balance is not None:
                    if not close(wallet, balance):
                        mismatches.append(f"{t['date']} {type_text} RM{amount:,.2f}")
                    wallet = balance

        if _match(type_key, SKIPPED):
            continue
        nice = NICE_TYPES.get(type_key, type_text)
        desc = re.sub(r"\s+", " ", _LONG_NUMBER.sub("", " ".join(t["desc"]))).strip()
        st.transactions.append(Transaction(
            d, ACCOUNT, value, f"{nice}: {desc}" if desc else nice, key=desc or nice))

    if unknown:
        st.warnings.append(
            "Unrecognised TNG transaction type(s), treated as money out: " + ", ".join(sorted(unknown)))
    st.check_ok = not mismatches and not unknown
    st.check = (
        "Wallet balance matched after every transaction."
        if not mismatches
        else f"Wallet balance did not match after {len(mismatches)} transaction(s), e.g. "
        + "; ".join(mismatches[:5]) + "."
    )
    if wallet is not None:
        st.check += f" Final wallet balance {money(wallet)}."
    return st
