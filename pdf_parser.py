import re
from datetime import datetime
import pdfplumber

SO_RE = re.compile(r"Order No\.\s*\n?\s*(SO-[\w-]+)")
PRO_RE = re.compile(r"\bPRO-[\w-]+\b")
COMPANY_RE = re.compile(r"Source Name\s+(.*?)\s+Stove Rating")
QTY_RE = re.compile(r"Quantity\s+(\d+)\s+\S+\s+Parent Work Centre")
DUE_DATE_RE = re.compile(r"Due Date\s+(\d{1,2}/\d{1,2}/\d{2,4})\s+Colour")


class PdfExtractionError(Exception):
    pass


def _parse_type(text: str) -> str:
    """The 'Type' is the first word of the line immediately above the
    'Due Date ... Colour' line (e.g. 'SolidCore with Duracote Skins, ...')."""
    lines = [l.strip() for l in text.split("\n")]
    for i, line in enumerate(lines):
        if line.startswith("Due Date") and i > 0:
            prev = lines[i - 1].strip()
            if prev:
                return prev.split()[0]
    return ""


def _parse_date(date_str: str) -> str:
    """Source dates are DD/MM/YY or DD/MM/YYYY. Returns ISO 'YYYY-MM-DD'."""
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise PdfExtractionError(f"Unrecognised date format: {date_str}")


def extract_fields(pdf_bytes_or_path) -> dict:
    with pdfplumber.open(pdf_bytes_or_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    so_match = SO_RE.search(text)
    pro_match = PRO_RE.search(text)
    company_match = COMPANY_RE.search(text)
    qty_match = QTY_RE.search(text)
    due_match = DUE_DATE_RE.search(text)

    missing = [
        name
        for name, m in (
            ("Order No. (SO)", so_match),
            ("PRO number", pro_match),
            ("Source Name (Company)", company_match),
            ("Quantity", qty_match),
            ("Due Date", due_match),
        )
        if not m
    ]
    if missing:
        raise PdfExtractionError(
            "Could not find the following field(s) in the PDF: " + ", ".join(missing)
        )

    return {
        "so": so_match.group(1),
        "pro": pro_match.group(0),
        "company": company_match.group(1).strip(),
        "qty": int(qty_match.group(1)),
        "type": _parse_type(text),
        "shipping_date": _parse_date(due_match.group(1)),
    }
