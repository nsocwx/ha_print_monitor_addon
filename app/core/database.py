"""Database setup and session management."""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy import inspect, text
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
    _migrate_existing_tables()


def _migrate_existing_tables():
    """Apply lightweight SQLite migrations for existing installs."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    migrations = {
        "printer_events": [
            ("printer_id", "TEXT NOT NULL DEFAULT 'default'"),
            ("printer_name", "TEXT NOT NULL DEFAULT 'Default Printer'"),
        ],
        "camera_captures": [
            ("printer_id", "TEXT NOT NULL DEFAULT 'default'"),
            ("printer_name", "TEXT NOT NULL DEFAULT 'Default Printer'"),
        ],
    }

    with engine.begin() as connection:
        for table_name, columns in migrations.items():
            if table_name not in existing_tables:
                continue

            existing_columns = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
            for column_name, column_sql in columns:
                if column_name not in existing_columns:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
                    )


def get_session():
    """Get database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
