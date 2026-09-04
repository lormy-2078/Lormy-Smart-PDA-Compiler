import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "pda_platform.db"
RATE_SEED_PATH = BASE_DIR / "data" / "rate_library_takoradi_clinker.json"
TARIFF_REF_SEED_PATH = BASE_DIR / "data" / "gpha_tariff_reference.json"
GMA_SAFETY_LEVY_SEED_PATH = BASE_DIR / "data" / "gma_safety_levy_reference.json"
GSA_SERVICE_CHARGE_SEED_PATH = BASE_DIR / "data" / "gsa_service_charge_reference.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
    port TEXT NOT NULL DEFAULT 'Takoradi',
    cargo_type TEXT NOT NULL DEFAULT 'Clinker',
    vessel_type TEXT DEFAULT 'Bulk Carrier',
    our_ref TEXT,
    your_ref TEXT,
    vessel TEXT,
    imo TEXT,
    flag TEXT,
    principal TEXT,
    principal_attn TEXT,
    receiver TEXT,
    receiver_attn TEXT,
    cargo_qty_mt REAL DEFAULT 0,
    grt REAL DEFAULT 0,
    loa REAL DEFAULT 0,
    draft REAL DEFAULT 0,
    port_stay_days REAL DEFAULT 0,
    port_stay_manual REAL DEFAULT 0,
    eta TEXT,
    movements_in_out INTEGER DEFAULT 2,
    movements_in INTEGER DEFAULT 1,
    movements_out INTEGER DEFAULT 1,
    shifting_movements INTEGER DEFAULT 0,
    anchorage_grt_days REAL DEFAULT 0,
    gangway_day_hours REAL DEFAULT 60,
    gangway_night_hours REAL DEFAULT 120,
    third_party_cost REAL DEFAULT 0,
    labour_delay_hours REAL DEFAULT 0,
    liner_terms TEXT DEFAULT '',
    appointment_text TEXT DEFAULT '',
    billing_decision TEXT,
    billing_reason TEXT,
    status TEXT DEFAULT 'draft',
    created_at TEXT,
    cargo_qty_cbm REAL DEFAULT 0,
    vessel_geared TEXT DEFAULT '',
    tally_total REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rate_table (
    rate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    charge_code TEXT NOT NULL,
    pda_type TEXT NOT NULL,
    description TEXT NOT NULL,
    basis TEXT NOT NULL,
    driver TEXT NOT NULL,
    amount REAL NOT NULL,
    unit_label TEXT,
    currency TEXT DEFAULT 'USD',
    source TEXT,
    tariff_ref_code TEXT,
    group_name TEXT DEFAULT 'Ship Related Expenses',
    cargo_match TEXT,
    grt_min REAL,
    grt_max REAL,
    minimum_amount REAL,
    liner_routing TEXT,
    active INTEGER DEFAULT 1
);

-- One row per Bill of Lading for cargoes whose Receiver PDA is prepared per-BL
-- rather than per-call (e.g. bagged Ammonium Nitrate via MAXAM Ghana, where a
-- single vessel call can have several BLs to different receivers/portions).
-- A call with zero rows here still gets exactly one Receiver PDA, priced off
-- the call's own cargo_qty_mt/receiver fields, matching every cargo built
-- before this -- BL rows are additive, not a replacement for that path.
CREATE TABLE IF NOT EXISTS bill_of_lading (
    bl_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL,
    bl_number TEXT,
    receiver TEXT,
    receiver_attn TEXT,
    cargo_qty_mt REAL DEFAULT 0,
    cargo_qty_cbm REAL DEFAULT 0,
    tally_amount REAL DEFAULT 0,
    bags REAL DEFAULT 0,
    cbm_multiplier REAL DEFAULT 0,
    created_at TEXT,
    FOREIGN KEY(call_id) REFERENCES calls(call_id)
);

CREATE TABLE IF NOT EXISTS tariff_reference (
    ref_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'rate',
    authority TEXT NOT NULL DEFAULT 'GPHA',
    schedule TEXT NOT NULL,
    schedule_page INTEGER,
    section TEXT NOT NULL,
    unit_label TEXT,
    code TEXT,
    description TEXT,
    rate_text TEXT,
    remarks TEXT,
    section_notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_tariff_code ON tariff_reference(code);
CREATE INDEX IF NOT EXISTS idx_tariff_authority ON tariff_reference(authority);
CREATE INDEX IF NOT EXISTS idx_tariff_schedule ON tariff_reference(schedule);

CREATE TABLE IF NOT EXISTS pda_lines (
    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL,
    pda_type TEXT NOT NULL,
    charge_code TEXT,
    description TEXT,
    basis TEXT,
    rate REAL,
    qty REAL,
    amount REAL,
    notes TEXT,
    FOREIGN KEY(call_id) REFERENCES calls(call_id)
);

CREATE TABLE IF NOT EXISTS documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER,
    doc_type TEXT,
    filename TEXT,
    stored_path TEXT,
    uploaded_at TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL,
    user TEXT,
    action TEXT,
    comment TEXT,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS outputs (
    output_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL,
    pda_type TEXT,
    format TEXT,
    file_path TEXT,
    created_at TEXT,
    version INTEGER DEFAULT 1
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_column(conn, table, column, coltype_and_default):
    """Additive migration: add `column` to `table` if it doesn't already exist.
    Never drops or recreates the database -- see feedback_db_schema_changes memory."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype_and_default}")


def _insert_tariff_rows(conn, seed_path):
    ref = json.loads(seed_path.read_text(encoding="utf-8"))
    for r in ref["rows"]:
        conn.execute(
            """INSERT INTO tariff_reference
               (kind, authority, schedule, schedule_page, section, unit_label, code, description, rate_text, remarks, section_notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (r["kind"], r["authority"], r["schedule"], r.get("schedule_page"), r["section"],
             r.get("unit_label"), r.get("code"), r.get("description"), r.get("rate_text"),
             r.get("remarks"), r.get("section_notes")),
        )


def _seed_tariff_authority_if_missing(conn, seed_path, authority):
    """Additive-only tariff_reference seed, scoped to one `authority`. Never
    touches rows belonging to any other authority (e.g. GPHA), regardless of
    the reseed_tariff_reference flag -- see feedback_db_schema_changes memory.
    Used on ordinary app startup -- does nothing once that authority has any rows."""
    if not seed_path.exists():
        return
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM tariff_reference WHERE authority = ?", (authority,)
    ).fetchone()["n"]
    if existing:
        return
    _insert_tariff_rows(conn, seed_path)
    conn.commit()


def refresh_tariff_authority(seed_path, authority):
    """Explicit refresh for when a source tariff document itself is updated
    (not called on ordinary startup, which uses _seed_tariff_authority_if_missing
    instead). Replaces every tariff_reference row for `authority` with the
    current contents of seed_path -- scoped strictly to that one authority, so
    it never touches any other authority's rows or any call/document data."""
    conn = get_conn()
    conn.execute("DELETE FROM tariff_reference WHERE authority = ?", (authority,))
    _insert_tariff_rows(conn, seed_path)
    conn.commit()
    conn.close()


def init_db(reseed_rates=False, reseed_tariff_reference=False):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    conn.executescript(SCHEMA)
    _ensure_column(conn, "rate_table", "tariff_ref_code", "TEXT")
    _ensure_column(conn, "rate_table", "group_name", "TEXT DEFAULT 'Ship Related Expenses'")
    _ensure_column(conn, "rate_table", "cargo_match", "TEXT")
    _ensure_column(conn, "rate_table", "grt_min", "REAL")
    _ensure_column(conn, "rate_table", "grt_max", "REAL")
    _ensure_column(conn, "rate_table", "minimum_amount", "REAL")
    _ensure_column(conn, "rate_table", "liner_routing", "TEXT")
    _ensure_column(conn, "calls", "liner_terms", "TEXT DEFAULT ''")
    _ensure_column(conn, "calls", "port_stay_manual", "REAL DEFAULT 0")
    _ensure_column(conn, "calls", "cargo_qty_cbm", "REAL DEFAULT 0")
    _ensure_column(conn, "calls", "vessel_geared", "TEXT DEFAULT ''")
    _ensure_column(conn, "calls", "tally_total", "REAL DEFAULT 0")
    _ensure_column(conn, "bill_of_lading", "bags", "REAL DEFAULT 0")
    _ensure_column(conn, "bill_of_lading", "cbm_multiplier", "REAL DEFAULT 0")
    conn.commit()

    count = conn.execute("SELECT COUNT(*) AS n FROM rate_table").fetchone()["n"]
    if count == 0 or reseed_rates:
        if reseed_rates:
            conn.execute("DELETE FROM rate_table")
        seed = json.loads(RATE_SEED_PATH.read_text(encoding="utf-8"))
        for r in seed["rates"]:
            conn.execute(
                """INSERT INTO rate_table
                   (charge_code, pda_type, description, basis, driver, amount, unit_label, currency, source, tariff_ref_code, group_name, cargo_match, grt_min, grt_max, minimum_amount, liner_routing, active)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r["charge_code"], r["pda_type"], r["description"], r["basis"], r["driver"],
                 r["amount"], r.get("unit_label"), seed.get("currency", "USD"),
                 r.get("source"), r.get("tariff_ref_code"), r.get("group", "Ship Related Expenses"),
                 r.get("cargo_match"), r.get("grt_min"), r.get("grt_max"),
                 r.get("minimum_amount"), r.get("liner_routing"), 1 if r.get("active", True) else 0),
            )
        conn.commit()

    tcount = conn.execute("SELECT COUNT(*) AS n FROM tariff_reference").fetchone()["n"]
    if (tcount == 0 or reseed_tariff_reference) and TARIFF_REF_SEED_PATH.exists():
        if reseed_tariff_reference:
            conn.execute("DELETE FROM tariff_reference")
        ref = json.loads(TARIFF_REF_SEED_PATH.read_text(encoding="utf-8"))
        for r in ref["rows"]:
            conn.execute(
                """INSERT INTO tariff_reference
                   (kind, authority, schedule, schedule_page, section, unit_label, code, description, rate_text, remarks, section_notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (r["kind"], r["authority"], r["schedule"], r.get("schedule_page"), r["section"],
                 r.get("unit_label"), r.get("code"), r.get("description"), r.get("rate_text"),
                 r.get("remarks"), r.get("section_notes")),
            )
        conn.commit()

    _seed_tariff_authority_if_missing(conn, GMA_SAFETY_LEVY_SEED_PATH, "GMA")
    _seed_tariff_authority_if_missing(conn, GSA_SERVICE_CHARGE_SEED_PATH, "GSA")
    conn.close()


def log_review(call_id, user, action, comment=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO reviews (call_id, user, action, comment, timestamp) VALUES (?,?,?,?,?)",
        (call_id, user, action, comment, now()),
    )
    conn.commit()
    conn.close()
