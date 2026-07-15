import sqlite3
from contextlib import contextmanager
from datetime import date

import workdays

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
    "make_progress", "press_progress", "cnc_progress",
]

PROGRESS_COLUMNS = {"make": "make_progress", "press": "press_progress", "cnc": "cnc_progress"}
DONE_COLUMNS = {"make": "make_done", "press": "press_done", "cnc": "cnc_done"}


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


DEFAULT_CAPACITIES = {"make_capacity": "24", "press_capacity": "24", "cnc_capacity": "24"}


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS so_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                so TEXT NOT NULL,
                pro TEXT UNIQUE,
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
                make_date TEXT,
                press_date TEXT,
                cnc_date TEXT,
                make_done INTEGER DEFAULT 0,
                press_done INTEGER DEFAULT 0,
                cnc_done INTEGER DEFAULT 0,
                make_progress INTEGER DEFAULT 0,
                press_progress INTEGER DEFAULT 0,
                cnc_progress INTEGER DEFAULT 0,
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        existing = conn.execute("SELECT COUNT(*) c FROM public_holidays").fetchone()["c"]
        if existing == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO public_holidays (date, name) VALUES (?, ?)",
                SEED_HOLIDAYS,
            )
        conn.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            list(DEFAULT_CAPACITIES.items()),
        )
        _migrate_unique_key_to_pro(conn)
        _migrate_add_stage_date_columns(conn)
        _migrate_add_progress_columns(conn)


def _migrate_unique_key_to_pro(conn):
    """One-off migration: earlier versions treated SO as the unique key (one
    row per sales order). Since a sales order can carry several PROs, PRO is
    now the unique key (one row per production item). Rebuilds the table in
    place if it still has the old constraint; existing rows are preserved."""
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='so_orders'"
    ).fetchone()["sql"]
    if "pro TEXT UNIQUE" in table_sql:
        return  # already migrated
    conn.execute("ALTER TABLE so_orders RENAME TO so_orders_old")
    conn.execute("""
        CREATE TABLE so_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            so TEXT NOT NULL,
            pro TEXT UNIQUE,
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
            make_date TEXT,
            press_date TEXT,
            cnc_date TEXT,
            make_done INTEGER DEFAULT 0,
            press_done INTEGER DEFAULT 0,
            cnc_done INTEGER DEFAULT 0,
            make_progress INTEGER DEFAULT 0,
            press_progress INTEGER DEFAULT 0,
            cnc_progress INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    old_columns = {row["name"] for row in conn.execute("PRAGMA table_info(so_orders_old)").fetchall()}
    has_stage_cols = {"make_date", "press_date", "cnc_date"} <= old_columns
    stage_cols_select = "make_date, press_date, cnc_date" if has_stage_cols else "NULL, NULL, NULL"
    has_progress_cols = {"make_progress", "press_progress", "cnc_progress"} <= old_columns
    progress_cols_select = "make_progress, press_progress, cnc_progress" if has_progress_cols else "0, 0, 0"
    conn.execute(f"""
        INSERT OR IGNORE INTO so_orders
            (so, pro, company, qty, type, shipping_date, urgent, paperwork,
             movement, posted, start_date, comments, make_date, press_date, cnc_date,
             make_done, press_done, cnc_done, make_progress, press_progress, cnc_progress,
             created_at, updated_at)
        SELECT so, pro, company, qty, type, shipping_date, urgent, paperwork,
               movement, posted, start_date, comments, {stage_cols_select},
               make_done, press_done, cnc_done, {progress_cols_select},
               created_at, updated_at
        FROM so_orders_old
    """)
    conn.execute("DROP TABLE so_orders_old")


def _migrate_add_stage_date_columns(conn):
    """Adds make_date/press_date/cnc_date to databases created before stage
    scheduling was stored, and backfills them from the existing formula so
    already-tracked orders land on today's default schedule."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(so_orders)").fetchall()}
    if "make_date" in columns:
        return
    conn.execute("ALTER TABLE so_orders ADD COLUMN make_date TEXT")
    conn.execute("ALTER TABLE so_orders ADD COLUMN press_date TEXT")
    conn.execute("ALTER TABLE so_orders ADD COLUMN cnc_date TEXT")

    holiday_dates = {
        date.fromisoformat(r["date"])
        for r in conn.execute("SELECT date FROM public_holidays").fetchall()
    }
    rows = conn.execute("SELECT id, shipping_date FROM so_orders").fetchall()
    for row in rows:
        if not row["shipping_date"]:
            continue
        stage = workdays.compute_stage_dates(row["shipping_date"], holiday_dates)
        conn.execute(
            "UPDATE so_orders SET make_date=?, press_date=?, cnc_date=? WHERE id=?",
            (
                stage["make"].isoformat() if stage["make"] else None,
                stage["press"].isoformat() if stage["press"] else None,
                stage["cnc"].isoformat() if stage["cnc"] else None,
                row["id"],
            ),
        )


def _migrate_add_progress_columns(conn):
    """Adds make_progress/press_progress/cnc_progress (units completed so
    far, entered from the mobile Scan tab) to databases created before
    quantity-based progress tracking existed. Backfills from the old
    all-or-nothing *_done flags so already-completed jobs show as 100%."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(so_orders)").fetchall()}
    if "make_progress" in columns:
        return
    conn.execute("ALTER TABLE so_orders ADD COLUMN make_progress INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE so_orders ADD COLUMN press_progress INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE so_orders ADD COLUMN cnc_progress INTEGER DEFAULT 0")
    conn.execute("UPDATE so_orders SET make_progress = qty WHERE make_done = 1")
    conn.execute("UPDATE so_orders SET press_progress = qty WHERE press_done = 1")
    conn.execute("UPDATE so_orders SET cnc_progress = qty WHERE cnc_done = 1")


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
    """Insert a new row per PRO, or update only the PDF-derived fields if that
    PRO already exists (manual fields like Urgent/Movement/Comments/done-flags
    are left untouched). PRO is the unique key: one sales order (SO) can
    contain several PROs, each tracked as its own row.

    `record` must include computed default make_date/press_date/cnc_date.
    Those defaults are only written on first insert, or if the Shipping Date
    changes on a re-upload -- otherwise a job's schedule stays wherever it was
    manually moved to on the Schedule tab."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, shipping_date FROM so_orders WHERE pro = ?", (record["pro"],)
        ).fetchone()
        if existing:
            if existing["shipping_date"] != record.get("shipping_date"):
                conn.execute(
                    """UPDATE so_orders SET so=?, company=?, qty=?, type=?, shipping_date=?,
                       make_date=?, press_date=?, cnc_date=?, updated_at=CURRENT_TIMESTAMP WHERE pro=?""",
                    (
                        record.get("so"),
                        record.get("company"),
                        record.get("qty"),
                        record.get("type"),
                        record.get("shipping_date"),
                        record.get("make_date"),
                        record.get("press_date"),
                        record.get("cnc_date"),
                        record["pro"],
                    ),
                )
            else:
                conn.execute(
                    """UPDATE so_orders SET so=?, company=?, qty=?, type=?,
                       shipping_date=?, updated_at=CURRENT_TIMESTAMP WHERE pro=?""",
                    (
                        record.get("so"),
                        record.get("company"),
                        record.get("qty"),
                        record.get("type"),
                        record.get("shipping_date"),
                        record["pro"],
                    ),
                )
            return existing["id"], "updated"
        else:
            cur = conn.execute(
                """INSERT INTO so_orders (so, pro, company, qty, type, shipping_date,
                   make_date, press_date, cnc_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("so"),
                    record["pro"],
                    record.get("company"),
                    record.get("qty"),
                    record.get("type"),
                    record.get("shipping_date"),
                    record.get("make_date"),
                    record.get("press_date"),
                    record.get("cnc_date"),
                ),
            )
            return cur.lastrowid, "inserted"


STAGE_DATE_COLUMNS = {"make": "make_date", "press": "press_date", "cnc": "cnc_date"}


def reschedule_stage(order_id: int, stage: str, new_date: str, holidays: set = None):
    """Manually move a job's Make/Press/CNC date (used by the Schedule tab).

    Make and Press are done by the same person on the same day, with CNC the
    next working day after. So moving Make also carries Press to the same
    date and CNC to the next working day. Moving Press or CNC on their own
    only moves that one stage -- the CNC person, say, can shift their day
    without disturbing Make/Press."""
    if stage not in STAGE_DATE_COLUMNS:
        raise ValueError(f"Unknown stage: {stage}")
    column = STAGE_DATE_COLUMNS[stage]
    with get_conn() as conn:
        conn.execute(
            f"UPDATE so_orders SET {column} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_date, order_id),
        )
        if stage == "make":
            cnc_date = workdays.workday(date.fromisoformat(new_date), 1, holidays or set())
            conn.execute(
                "UPDATE so_orders SET press_date = ?, cnc_date = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_date, cnc_date.isoformat(), order_id),
            )


def get_capacities() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('make_capacity', 'press_capacity', 'cnc_capacity')"
        ).fetchall()
        values = {r["key"]: int(r["value"]) for r in rows}
    return {
        "make": values.get("make_capacity", 24),
        "press": values.get("press_capacity", 24),
        "cnc": values.get("cnc_capacity", 24),
    }


def set_capacity(stage: str, value: int):
    if stage not in STAGE_DATE_COLUMNS:
        raise ValueError(f"Unknown stage: {stage}")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (f"{stage}_capacity", str(value)),
        )


def get_all_orders():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM so_orders ORDER BY shipping_date ASC").fetchall()
        return [dict(r) for r in rows]


def get_order_by_pro(pro: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM so_orders WHERE pro = ?", (pro,)).fetchone()
        return dict(row) if row else None


def update_progress(order_id: int, stage: str, qty_done: int):
    """Sets how many units of a stage are complete (used by the mobile Scan
    tab). Clamped to [0, qty]; the boolean *_done flag is kept in sync."""
    if stage not in PROGRESS_COLUMNS:
        raise ValueError(f"Unknown stage: {stage}")
    progress_col = PROGRESS_COLUMNS[stage]
    done_col = DONE_COLUMNS[stage]
    with get_conn() as conn:
        row = conn.execute("SELECT qty FROM so_orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ValueError(f"No order with id {order_id}")
        total = row["qty"] or 0
        clamped = max(0, min(int(qty_done), total))
        done = 1 if total > 0 and clamped >= total else 0
        conn.execute(
            f"UPDATE so_orders SET {progress_col} = ?, {done_col} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (clamped, done, order_id),
        )
        return clamped


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
