"""
database.py — SQLAlchemy engine setup and session management.

This module is imported by every screen that reads or writes data.
Usage:
    from core.database import get_session
    with get_session() as session:
        session.add(some_object)
        session.commit()
"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from core.models import Base

# ── Path to the SQLite database file ──────────────────────────────────────────
# Stored in the project root alongside main.py.
DB_PATH = Path(__file__).resolve().parent.parent / "reactor.db"
DB_URL  = f"sqlite:///{DB_PATH}"

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
    # Step 1: create any brand-new tables (idempotent)
    Base.metadata.create_all(bind=engine)

    # Step 2: apply incremental schema upgrades to existing tables
    from core.migrations import run_migrations
    run_migrations(engine)

    print(f"[Database] Ready — {DB_PATH}")


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
