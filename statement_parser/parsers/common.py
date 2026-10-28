import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# Reference codes and account numbers that add nothing to a description.
_NOISE = [
    re.compile(r"^(HIB-|LP ?-|REF |/EREF/|/REMI/)", re.I),
    re.compile(r"^[/VI|1]?(EREF|REMI)[/VI|1]?$", re.I),  # OCR reads the slashes as V, I, | or 1
    re.compile(r"^[A-Z]{0,6}\d{6,}[A-Z]?$"),  # e.g. QR12345678, 123456789Q, MBBQR1234567, 123456789012
    re.compile(r"^[\d\s]{8,}$"),
    re.compile(r"^(?=(?:\D*\d){10})\S+$"),  # one 'word' with 10+ digits, e.g. 123456789012345V100
    re.compile(r"^(?=\S*\d)(?=\S*-)\S{12,}$"),  # long codes with dashes: SA-CR-AB12CD34-EF56, UUIDs
    re.compile(r"^(?=(?:\D*\d){5})[A-Za-z0-9]{12,}$"),  # long letter-and-digit codes: 01ABCD2E3F4G56
    re.compile(r"^\d{1,3}$"),  # stray short numbers, e.g. a lone "00"
]


def is_noise(line: str) -> bool:
    return any(p.search(line) for p in _NOISE)


def clean_line(line: str) -> str:
    return re.sub(r"\s*\*$", "", line).strip()


def join_description(lines: list) -> str:
    """Joins description lines with ' | ', dropping reference codes and repeats."""
    kept = []
    for line in lines:
        line = clean_line(line)
        # Skip repeats, including shortened repeats ('ACME TRADING SDN B' after 'ACME TRADING SDN BHD').
        if line and not is_noise(line) and not any(k.upper().startswith(line.upper()) for k in kept):
            kept.append(line)
    return " | ".join(kept)


def sentence_case(text: str) -> str:
    """'SHELL - SEA PARK PJ | DUITNOW QR' -> 'Shell - sea park pj | Duitnow qr'.
    Each ' | ' part starts with a capital; currency codes in brackets like '(3.66 USD)' stay upper case."""
    parts = []
    for part in text.split(" | "):
        part = part.lower()
        # Inside brackets, a 3-letter code after an amount is a currency: '(85.00 thb, fee 1.00 myr)'.
        part = re.sub(r"\([^)]*\)", lambda b: re.sub(
            r"(\d\.\d{2}) ([a-z]{3})\b", lambda m: f"{m.group(1)} {m.group(2).upper()}", b.group(0)), part)
        parts.append(part[:1].upper() + part[1:])
    return " | ".join(parts)


def month_number(text: str) -> int:
    """'OCT', 'Oct', and OCR misreads like '0CT' or 'Ju1' / 'Ju|' (for Jul) -> month number."""
    name = text.upper().replace("0", "O")[:3]
    if name not in MONTHS and name[:2] == "JU":
        name = "JUL"  # the only month whose 3rd letter (L) OCR mistakes for 1, | or I
    if name not in MONTHS:
        raise ValueError(f"Could not read the month '{text}'.")
    return MONTHS[name]


def infer_year(day: int, month: int, statement_date: date) -> date:
    """Card statements omit the year; a month after the statement month belongs to last year."""
    year = statement_date.year if month <= statement_date.month else statement_date.year - 1
    return date(year, month, day)


def money(x: float) -> str:
    return f"{x:,.2f}"


def close(a: float, b: float) -> bool:
    return abs(a - b) < 0.005
