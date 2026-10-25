"""
Database Session and Engine Management Module.

Configures SQLAlchemy engine, session maker, and connection pragmas
to guarantee transactional integrity and strict foreign key enforcement.
"""

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

# Create database engine. Connect args needed for SQLite concurrency and threading.
connect_args = {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,
    future=True,
)


# Enforce foreign key constraints on SQLite connections
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Enables SQLite foreign key enforcement and Write-Ahead Logging (WAL)
    for high concurrent read performance.
    """
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


# Session factory for generating request-scoped database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Declarative base model for ORM mapping
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a clean SQLAlchemy session per request
    and guarantees proper closure and cleanup upon completion.

    Yields:
        Session: Active SQLAlchemy database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
