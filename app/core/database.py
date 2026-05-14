"""Database setup and session management."""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATABASE_URL = f"sqlite:///{DATA_DIR}/app.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(
    class_=Session,
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db():
    """Initialize database tables."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """Get database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
