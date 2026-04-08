"""
database.py — SQLAlchemy engine setup and session management.

This module is imported by every screen that reads or writes data.
Usage:
    from core.database import get_session
    with get_session() as session:
        session.add(some_object)
        session.commit()
"""

import shutil
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from core.models import Base
from core.paths import DB_PATH  # noqa: F401 — re-exported so other modules can do: from core.database import DB_PATH

DB_URL = f"sqlite:///{DB_PATH}"

# ── Create engine ─────────────────────────────────────────────────────────────
# echo=False keeps SQL queries out of the console in production.
# Set echo=True temporarily if you need to debug a query.
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})

# ── Session factory ───────────────────────────────────────────────────────────
# Call get_session() wherever you need database access.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """
    Create all tables defined in models.py if they do not already exist,
    then run any pending schema migrations to upgrade an existing database.

    Called once at application startup from main.py.
    Safe to call repeatedly — it will never drop or overwrite existing data.
    Existing rows in reactor.db are preserved across app updates.
    """
    # Step 1: first-run data migration
    # If reactor.db doesn't yet exist in AppData but there is one sitting next
    # to the executable (the old dev/pre-packaging location), copy it across
    # automatically so no research data is lost on the first update.
    if not DB_PATH.exists():
        _migrate_legacy_db()

    # Step 2: create any brand-new tables (idempotent)
    Base.metadata.create_all(bind=engine)

    # Step 3: apply incremental schema upgrades to existing tables
    from core.migrations import run_migrations
    run_migrations(engine)

    print(f"[Database] Ready — {DB_PATH}")


def _migrate_legacy_db() -> None:
    """
    One-time migration: copy reactor.db from the old location (next to the
    executable / project root) to the new AppData location.

    Runs silently — if no legacy database is found, nothing happens.
    """
    candidates = [
        # Next to the running executable (packaged .exe)
        Path(sys.executable).parent / "reactor.db",
        # Project root during development
        Path(__file__).resolve().parent.parent / "reactor.db",
    ]
    for old_path in candidates:
        if old_path.exists() and old_path != DB_PATH:
            shutil.copy2(old_path, DB_PATH)
            print(f"[Database] Migrated existing database from {old_path} → {DB_PATH}")
            return


@contextmanager
def get_session() -> Session:
    """
    Context manager that yields a database session and handles
    commit/rollback/close automatically.

    Example:
        with get_session() as session:
            results = session.query(Experiment).all()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
