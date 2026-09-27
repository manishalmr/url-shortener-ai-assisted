"""
Database engine/session setup.

Uses SQLAlchemy 2.0 style. SQLite is used by default for local development;
switching to Postgres in another environment (e.g. staging/prod) only
requires changing DATABASE_URL - no application code changes needed.
"""
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# SQLite needs check_same_thread=False when used with FastAPI's threaded
# request handling; this flag is a no-op for other database backends.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

if settings.database_url.startswith("sqlite:///./"):
    db_path = Path(settings.database_url.replace("sqlite:///./", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency yielding a request-scoped DB session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they do not already exist (dev/test convenience)."""
    from app import models  # noqa: F401  (ensure models are registered on Base)

    Base.metadata.create_all(bind=engine)
