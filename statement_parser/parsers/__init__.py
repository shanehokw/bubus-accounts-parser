from pathlib import Path

from ..pdf_text import first_page_text, is_picture, ocr_rows, text_rows
from . import hsbc_cc, hsbc_savings, maybank_cc, maybank_savings, rhb_savings, sc_cc, tng
from .common import sentence_case

# Checked in order; Maybank savings is checked before the card because the card's
# first page does not say "ACCOUNT TRANSACTIONS".
_TEXT_PARSERS = [maybank_savings, maybank_cc, sc_cc, rhb_savings]
_ROW_PARSERS = [tng, hsbc_savings, hsbc_cc]


def parse_statement(path: Path, password: str = ""):
    """Detects the statement type and parses it. Raises PasswordRequired or ValueError."""
    statement = _parse(path, password)
    for t in statement.transactions:
        t.description = sentence_case(t.description)
    return statement


def _parse(path: Path, password: str):
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
    if is_picture(path, password):
        raise ValueError(
            "This PDF is a picture of a statement (for example printed or saved from an email "
            "preview), not the bank's own PDF. Download the original PDF attachment instead."
        )
    raise ValueError(
        "Unrecognised statement. Supported: Maybank Savings, Maybank Credit Card, "
        "HSBC Savings, HSBC Credit Card, SC Credit Card, RHB Savings, TNG eWallet."
    )
