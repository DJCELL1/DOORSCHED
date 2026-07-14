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


def _group_pages_into_orders(page_texts: list) -> list:
    """A single printout can contain several orders/PROs stacked back to back.
    A page starts a NEW block if it introduces its own 'Order No.' section, or
    if it shows a different PRO number than the block currently being built
    (some combined printouts repeat the PRO/Due Date/Quantity per component
    without re-printing the SO-level 'Order No.' header). Plain continuation
    pages (extra component listings that repeat the same PRO) stay attached to
    the block they follow."""
    blocks = []
    current = []
    current_pro = None
    for text in page_texts:
        pro_match = PRO_RE.search(text)
        page_pro = pro_match.group(0) if pro_match else None
        starts_new_order = bool(SO_RE.search(text))
        starts_new_pro = page_pro is not None and current_pro is not None and page_pro != current_pro
        if current and (starts_new_order or starts_new_pro):
            blocks.append(current)
            current = []
        current.append(text)
        if page_pro:
            current_pro = page_pro
    if current:
        blocks.append(current)
    return blocks


def _extract_from_text(text: str, fallback_so=None, fallback_company=None) -> dict:
    so_match = SO_RE.search(text)
    pro_match = PRO_RE.search(text)
    company_match = COMPANY_RE.search(text)
    qty_match = QTY_RE.search(text)
    due_match = DUE_DATE_RE.search(text)

    so_value = so_match.group(1) if so_match else fallback_so
    company_value = company_match.group(1).strip() if company_match else fallback_company

    missing = [
        name
        for name, val in (
            ("Order No. (SO)", so_value),
            ("PRO number", pro_match),
            ("Source Name (Company)", company_value),
            ("Quantity", qty_match),
            ("Due Date", due_match),
        )
        if not val
    ]
    if missing:
        raise PdfExtractionError(
            "Could not find the following field(s): " + ", ".join(missing)
        )

    return {
        "so": so_value,
        "pro": pro_match.group(0),
        "company": company_value,
        "qty": int(qty_match.group(1)),
        "type": _parse_type(text),
        "shipping_date": _parse_date(due_match.group(1)),
    }


def extract_all_records(pdf_bytes_or_path) -> list:
    """Parses one PDF that may hold one or several sales orders/PROs (combined
    printouts) into a list of order dicts, one per order/PRO."""
    with pdfplumber.open(pdf_bytes_or_path) as pdf:
        page_texts = [page.extract_text() or "" for page in pdf.pages]

    blocks = _group_pages_into_orders(page_texts)

    records = []
    errors = []
    last_so = None
    last_company = None
    for block in blocks:
        combined = "\n".join(block)
        try:
            record = _extract_from_text(combined, fallback_so=last_so, fallback_company=last_company)
        except PdfExtractionError as e:
            errors.append(str(e))
            continue
        records.append(record)
        last_so = record["so"]
        last_company = record["company"]

    if not records:
        raise PdfExtractionError("; ".join(errors) or "No sales orders found in PDF")
    return records


def extract_fields(pdf_bytes_or_path) -> dict:
    """Back-compat single-order helper: returns the first order found."""
    return extract_all_records(pdf_bytes_or_path)[0]
