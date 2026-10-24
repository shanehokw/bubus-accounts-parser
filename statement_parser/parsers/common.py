import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# Reference codes and account numbers that add nothing to a description.
_NOISE = [
    re.compile(r"^(HIB-|LP ?-|REF |/EREF/|/REMI/)", re.I),
    re.compile(r"^[A-Z]{0,6}\d{6,}[A-Z]?$"),  # e.g. QR12345678, 123456789Q, MBBQR1234567, 123456789012
    re.compile(r"^[\d\s]{8,}$"),
    re.compile(r"^(?=(?:\D*\d){10})\S+$"),  # one 'word' with 10+ digits, e.g. 123456789012345V100
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
        if line and not is_noise(line) and line.upper() not in (k.upper() for k in kept):
            kept.append(line)
    return " | ".join(kept)


def sentence_case(text: str) -> str:
    """'SHELL - SEA PARK PJ | DUITNOW QR' -> 'Shell - sea park pj | Duitnow qr'.
    Each ' | ' part starts with a capital; currency codes like '(3.66 USD)' stay upper case."""
    parts = []
    for part in text.split(" | "):
        part = part.lower()
        part = re.sub(r"\(([\d,.]+) ([a-z]{3})\)", lambda m: f"({m.group(1)} {m.group(2).upper()})", part)
        parts.append(part[:1].upper() + part[1:])
    return " | ".join(parts)


def month_number(text: str) -> int:
    """'OCT', 'Oct', '0CT' (OCR) -> 10."""
    return MONTHS[text.upper().replace("0", "O")[:3]]


def infer_year(day: int, month: int, statement_date: date) -> date:
    """Card statements omit the year; a month after the statement month belongs to last year."""
    year = statement_date.year if month <= statement_date.month else statement_date.year - 1
    return date(year, month, day)


def money(x: float) -> str:
    return f"{x:,.2f}"


def close(a: float, b: float) -> bool:
    return abs(a - b) < 0.005
