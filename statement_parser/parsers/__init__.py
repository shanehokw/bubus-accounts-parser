from pathlib import Path

from ..pdf_text import first_page_text, ocr_rows, text_rows
from . import hsbc_cc, hsbc_savings, maybank_cc, maybank_savings, tng

# Checked in order; Maybank savings is checked before the card because the card's
# first page does not say "ACCOUNT TRANSACTIONS".
_TEXT_PARSERS = [maybank_savings, maybank_cc]
_ROW_PARSERS = [tng, hsbc_savings, hsbc_cc]


def parse_statement(path: Path, password: str = ""):
    """Detects the statement type and parses it. Raises PasswordRequired or ValueError."""
    first_page = first_page_text(path, password)
    rows = None
    if not first_page:
        rows = ocr_rows(path, password)
        first_page = "\n".join(r.text for r in rows if r.page == 0)

    for parser in _TEXT_PARSERS:
        if parser.matches(first_page):
            return parser.parse(path, password)
    for parser in _ROW_PARSERS:
        if parser.matches(first_page):
            return parser.parse(rows if rows is not None else text_rows(path, password))
    raise ValueError(
        "Unrecognised statement. Supported: Maybank Savings, Maybank Credit Card, "
        "HSBC Savings, HSBC Credit Card, TNG eWallet."
    )
