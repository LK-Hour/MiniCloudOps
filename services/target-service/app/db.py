"""Database engine and session. This service only ever talks to its own database."""
import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_is_ready() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database readiness check failed")
        return False


def init_db() -> None:
    """Create tables on startup. TODO: replace with Alembic migrations."""
    from app import models  # noqa: F401  (registers the models on Base.metadata)

    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ensured")
    except Exception:
        logger.exception("Could not create database tables; will retry on next start")
