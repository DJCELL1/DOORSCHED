import sqlite3
from contextlib import contextmanager

DB_PATH = "so_tracker.db"

# Seed WA public holidays (source: payly.com.au WA calendars, fetched 2026-07-14).
# Editable later from the Public Holidays tab in the app.
SEED_HOLIDAYS = [
    ("2026-01-01", "New Year's Day"),
    ("2026-01-26", "Australia Day"),
    ("2026-03-02", "Labour Day"),
    ("2026-04-03", "Good Friday"),
    ("2026-04-05", "Easter Sunday"),
    ("2026-04-06", "Easter Monday"),
    ("2026-04-25", "ANZAC Day"),
    ("2026-04-27", "ANZAC Day Observed"),
    ("2026-06-01", "Western Australia Day"),
    ("2026-09-28", "King's Birthday"),
    ("2026-12-25", "Christmas Day"),
    ("2026-12-26", "Boxing Day"),
    ("2026-12-28", "Boxing Day Observed"),
    ("2027-01-01", "New Year's Day"),
    ("2027-01-26", "Australia Day"),
    ("2027-03-01", "Labour Day"),
    ("2027-03-26", "Good Friday"),
    ("2027-03-28", "Easter Sunday"),
    ("2027-03-29", "Easter Monday"),
    ("2027-04-25", "ANZAC Day"),
    ("2027-04-26", "ANZAC Day Observed"),
    ("2027-06-07", "Western Australia Day"),
    ("2027-09-27", "King's Birthday"),
    ("2027-12-25", "Christmas Day"),
    ("2027-12-26", "Boxing Day"),
    ("2027-12-28", "Boxing Day Observed"),
    ("2028-01-01", "New Year's Day"),
    ("2028-01-26", "Australia Day"),
    ("2028-03-06", "Labour Day"),
    ("2028-04-14", "Good Friday"),
    ("2028-04-16", "Easter Sunday"),
    ("2028-04-17", "Easter Monday"),
    ("2028-04-25", "ANZAC Day"),
    ("2028-06-05", "Western Australia Day"),
    ("2028-09-25", "King's Birthday"),
    ("2028-12-25", "Christmas Day"),
    ("2028-12-26", "Boxing Day"),
]

# Columns that come from the PDF and get overwritten on re-upload of the same SO.
PDF_FIELDS = ["pro", "company", "qty", "type", "shipping_date"]

# Columns the user edits by hand; preserved when an SO is re-uploaded.
MANUAL_FIELDS = [
    "urgent", "paperwork", "movement", "posted", "start_date", "comments",
    "make_done", "press_done", "cnc_done",
]


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS so_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                so TEXT UNIQUE NOT NULL,
                pro TEXT,
                company TEXT,
                qty INTEGER,
                type TEXT,
                shipping_date TEXT,
                urgent INTEGER DEFAULT 0,
                paperwork INTEGER DEFAULT 0,
                movement TEXT DEFAULT '',
                posted TEXT DEFAULT '',
                start_date TEXT DEFAULT '',
                comments TEXT DEFAULT '',
                make_done INTEGER DEFAULT 0,
                press_done INTEGER DEFAULT 0,
                cnc_done INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS public_holidays (
                date TEXT PRIMARY KEY,
                name TEXT
            )
        """)
        existing = conn.execute("SELECT COUNT(*) c FROM public_holidays").fetchone()["c"]
        if existing == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO public_holidays (date, name) VALUES (?, ?)",
                SEED_HOLIDAYS,
            )


def get_holidays():
    with get_conn() as conn:
        rows = conn.execute("SELECT date, name FROM public_holidays ORDER BY date").fetchall()
        return [dict(r) for r in rows]


def add_holiday(date_str, name):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO public_holidays (date, name) VALUES (?, ?)",
            (date_str, name),
        )


def delete_holiday(date_str):
    with get_conn() as conn:
        conn.execute("DELETE FROM public_holidays WHERE date = ?", (date_str,))


def upsert_so(record: dict):
    """Insert a new SO row, or update only the PDF-derived fields if the SO
    already exists (manual fields like Urgent/Movement/Comments/done-flags
    are left untouched)."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM so_orders WHERE so = ?", (record["so"],)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE so_orders SET pro=?, company=?, qty=?, type=?,
                   shipping_date=?, updated_at=CURRENT_TIMESTAMP WHERE so=?""",
                (
                    record.get("pro"),
                    record.get("company"),
                    record.get("qty"),
                    record.get("type"),
                    record.get("shipping_date"),
                    record["so"],
                ),
            )
            return existing["id"], "updated"
        else:
            cur = conn.execute(
                """INSERT INTO so_orders (so, pro, company, qty, type, shipping_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record["so"],
                    record.get("pro"),
                    record.get("company"),
                    record.get("qty"),
                    record.get("type"),
                    record.get("shipping_date"),
                ),
            )
            return cur.lastrowid, "inserted"


def get_all_orders():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM so_orders ORDER BY shipping_date ASC").fetchall()
        return [dict(r) for r in rows]


def update_order_field(so_id: int, field: str, value):
    allowed = set(MANUAL_FIELDS)
    if field not in allowed:
        raise ValueError(f"Field {field} is not editable")
    with get_conn() as conn:
        conn.execute(
            f"UPDATE so_orders SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, so_id),
        )


def update_order_row(so_id: int, fields: dict):
    allowed = set(MANUAL_FIELDS)
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"Fields not editable: {bad}")
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE so_orders SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*fields.values(), so_id),
        )


def delete_order(so_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM so_orders WHERE id = ?", (so_id,))
