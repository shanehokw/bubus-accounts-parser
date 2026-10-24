"""Reading PDFs as text rows, either from the PDF's own text or via the offline OCR helper."""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect

OCR_DIR = Path(__file__).parent / "ocr"
OCR_SOURCE = OCR_DIR / "pdf_ocr.swift"
OCR_BINARY = OCR_DIR / "pdf_ocr"


class PasswordRequired(Exception):
    pass


@dataclass
class Segment:
    x0: float
    x1: float
    text: str


@dataclass
class Row:
    page: int
    y: float
    segments: list

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)


def open_pdf(path: Path, password: str = ""):
    try:
        pdf = pdfplumber.open(path, password=password or None)
        pdf.pages  # forces decryption
        return pdf
    except PDFPasswordIncorrect as e:
        raise PasswordRequired() from e
    except Exception as e:
        if "password" in str(e).lower() or "encrypt" in str(e).lower():
            raise PasswordRequired() from e
        raise


def first_page_text(path: Path, password: str = "") -> str:
    """The first page's own text, or '' if the PDF has no text layer (e.g. HSBC)."""
    with open_pdf(path, password) as pdf:
        page = pdf.pages[0]
        return (page.extract_text() or "") if len(page.chars) > 20 else ""


def is_picture(path: Path, password: str = "") -> bool:
    """True when the first page is mostly one image, e.g. a statement printed from an email preview."""
    with open_pdf(path, password) as pdf:
        page = pdf.pages[0]
        image_area = sum(i["width"] * i["height"] for i in page.images)
        return image_area > 0.5 * page.width * page.height


def page_lines(path: Path, password: str = "", x_tolerance: float = 3) -> list:
    """The PDF's own text, as a list of lines per page. Lower x_tolerance for PDFs whose
    letters sit close together, so words don't run into each other."""
    with open_pdf(path, password) as pdf:
        return [(page.extract_text(x_tolerance=x_tolerance) or "").splitlines() for page in pdf.pages]


def text_rows(path: Path, password: str = "") -> list:
    """The PDF's own text, as rows of words with positions."""
    rows = []
    with open_pdf(path, password) as pdf:
        for n, page in enumerate(pdf.pages):
            words = [
                (w["x0"], w["x1"], (w["top"] + w["bottom"]) / 2, w["text"])
                for w in page.extract_words()
            ]
            rows += _group_rows(n, words)
    return rows


def ocr_rows(path: Path, password: str = "") -> list:
    """Text read from page images with macOS's built-in OCR, as rows of text pieces."""
    _ensure_ocr_binary()
    args = [str(OCR_BINARY), str(path)] + ([password] if password else [])
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        if "PASSWORD_REQUIRED" in result.stderr:
            raise PasswordRequired()
        raise RuntimeError(f"OCR failed: {result.stderr.strip()}")
    rows = []
    for n, page in enumerate(json.loads(result.stdout)["pages"]):
        pieces = [
            (l["x0"], l["x1"], (l["y0"] + l["y1"]) / 2, normalise_ocr(l["text"]))
            for l in page["lines"]
        ]
        rows += _group_rows(n, pieces)
    return rows


def _group_rows(page: int, pieces: list, tolerance: float = 3.5) -> list:
    rows = []
    for x0, x1, y, text in sorted(pieces, key=lambda p: p[2]):
        if rows and abs(rows[-1].y - y) < tolerance:
            rows[-1].segments.append(Segment(x0, x1, text))
        else:
            rows.append(Row(page, y, [Segment(x0, x1, text)]))
    for row in rows:
        row.segments.sort(key=lambda s: s.x0)
    return rows


def _ensure_ocr_binary():
    if OCR_BINARY.exists() and OCR_BINARY.stat().st_mtime >= OCR_SOURCE.stat().st_mtime:
        return
    result = subprocess.run(
        ["swiftc", "-O", str(OCR_SOURCE), "-o", str(OCR_BINARY)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Could not build the OCR helper. Install Xcode Command Line Tools "
            f"(xcode-select --install).\n{result.stderr}"
        )


# OCR sometimes returns Cyrillic or Greek letters that look like Latin ones.
_LOOKALIKES = str.maketrans("АВСЕНКМОРТХЗаеорсухіІ", "ABCEHKMOPTX3aeopcyxiI")


def normalise_ocr(text: str) -> str:
    return text.translate(_LOOKALIKES)


def parse_amount(text: str) -> float:
    """'1,234.56' -> 1234.56. Tolerates OCR reading a comma as a dot ('1.234.56')."""
    digits = re.sub(r"[^\d.]", "", text)
    if digits.count(".") > 1:
        head, _, tail = digits.rpartition(".")
        digits = head.replace(".", "") + "." + tail
    return float(digits)
