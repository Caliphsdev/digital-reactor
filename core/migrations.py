"""
migrations.py — Incremental database schema migration runner.

HOW IT WORKS
------------
A `schema_version` table holds a single integer row that tracks how many
migrations have been applied.  On every app startup (called from init_db)
this module compares that number against CURRENT_SCHEMA_VERSION and runs
only the missing migrations in order.

This means:
  • Existing reactor.db data is NEVER lost when you update the app.
  • New columns are added with NULL defaults — old rows are untouched.
  • Each migration function is idempotent (safe to run twice via
    "IF NOT EXISTS" / "IF column not exists" guards).

ADDING A NEW MIGRATION
----------------------
1. Write a function  migration_NNN_description(conn)  that uses raw SQL
   (conn.execute / conn.executescript) — SQLAlchemy text() is fine too.
2. Append it to the MIGRATIONS list as (version_number, function).
3. Bump CURRENT_SCHEMA_VERSION to match the highest version number.

Never modify or delete existing migrations — only append new ones.
"""

from sqlalchemy import text


# ── Version tracking ──────────────────────────────────────────────────────────
CURRENT_SCHEMA_VERSION = 2   # increment each time a migration is added


# ── Individual migration functions ────────────────────────────────────────────

def migration_001_add_advanced_daily_params(conn) -> None:
    """
    v1 — Add Tier-1 research parameters to the daily_readings table.

    New columns (all REAL, nullable):
      vss_mgl        — Volatile Suspended Solids (mg/L)
      tss_mgl        — Total Suspended Solids (mg/L)
      orp_mv         — Oxidation-Reduction Potential (mV)
      alkalinity_mgl — Alkalinity as CaCO3 (mg/L)
      turbidity_ntu  — Turbidity (NTU)
      our_mgl_h      — Oxygen Uptake Rate (mg/L/h)
      bod_mgl        — Biochemical Oxygen Demand (mg/L)
      tn_mgl         — Total Nitrogen (mg/L)
      tp_mgl         — Total Phosphorus (mg/L)

    Uses SQLite's "ALTER TABLE ADD COLUMN IF NOT EXISTS" pattern via
    a try/except to stay compatible with older SQLite versions.
    """
    new_columns = [
        ("vss_mgl",        "REAL"),
        ("tss_mgl",        "REAL"),
        ("orp_mv",         "REAL"),
        ("alkalinity_mgl", "REAL"),
        ("turbidity_ntu",  "REAL"),
        ("our_mgl_h",      "REAL"),
        ("bod_mgl",        "REAL"),
        ("tn_mgl",         "REAL"),
        ("tp_mgl",         "REAL"),
    ]
    for col_name, col_type in new_columns:
        try:
            conn.execute(
                text(f"ALTER TABLE daily_readings ADD COLUMN {col_name} {col_type}")
            )
        except Exception:
            # Column already exists — safe to ignore
            pass


def migration_002_add_sludge_characterization(conn) -> None:
    """
    v2 — Create the sludge_characterization table for weekly SVI tests.

    Tracks settleability and biomass data that is measured weekly
    (not daily), separate from the daily_readings table.
    """
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sludge_characterization (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id    INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
            test_date        DATE    NOT NULL,
            zone             TEXT    NOT NULL DEFAULT 'aerobic',
            svi_30_ml_g      REAL,
            svi_5_ml_g       REAL,
            tsv_ml           REAL,
            settleability_pct REAL,
            notes            TEXT,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))


# ── Migration registry ─────────────────────────────────────────────────────────
# Each entry: (version_number, migration_function)
# APPEND ONLY — never remove or reorder existing entries.
MIGRATIONS: list[tuple[int, object]] = [
    (1, migration_001_add_advanced_daily_params),
    (2, migration_002_add_sludge_characterization),
]


# ── Runner ────────────────────────────────────────────────────────────────────

def _ensure_version_table(conn) -> None:
    """Create the schema_version table and seed it with 0 if absent."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_version (
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL DEFAULT 0
        )
    """))
    conn.execute(text("""
        INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, 0)
    """))


def _get_version(conn) -> int:
    result = conn.execute(text("SELECT version FROM schema_version WHERE id = 1"))
    row = result.fetchone()
    return row[0] if row else 0


def _set_version(conn, version: int) -> None:
    conn.execute(
        text("UPDATE schema_version SET version = :v WHERE id = 1"),
        {"v": version}
    )


def run_migrations(engine) -> None:
    """
    Apply any pending schema migrations in version order.

    Called once at startup from database.init_db() — after Base.metadata
    create_all() so all original tables already exist before we alter them.

    Args:
        engine: SQLAlchemy Engine connected to reactor.db
    """
    with engine.begin() as conn:
        _ensure_version_table(conn)
        current = _get_version(conn)

        if current >= CURRENT_SCHEMA_VERSION:
            return   # already up to date

        for version, fn in MIGRATIONS:
            if version > current:
                print(f"[Migrations] Applying migration v{version}: {fn.__name__}")
                fn(conn)
                _set_version(conn, version)

        print(f"[Migrations] Schema is now at v{CURRENT_SCHEMA_VERSION}")
