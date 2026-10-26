import os
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'clinical_compass.db'}")
if not DATABASE_URL.startswith("sqlite"):
    raise RuntimeError("Клинический компас поддерживает только SQLite")
CONNECT_ARGS = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=CONNECT_ARGS)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def check_connection() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def ensure_schema() -> None:
    """Apply safe additive migrations to the local SQLite database."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if not existing_tables:
        return

    if "users" not in existing_tables:
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as connection:
        if "email" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(254)"))
        if "phone" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN phone VARCHAR(32)"))
        if engine.dialect.name == "sqlite":
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone ON users (phone)"))

    sqlite_columns: dict[str, dict[str, str]] = {
        "patient_profiles": {
            "first_two_lines_refractory": "BOOLEAN NOT NULL DEFAULT 0",
            "contraindications_reviewed": "BOOLEAN NOT NULL DEFAULT 0",
            "safety_reviewed_at": "DATETIME",
            "medication_restrictions_json": "TEXT NOT NULL DEFAULT '{}'",
        },
        "questionnaire_assignments": {
            "version_id": "VARCHAR(36)",
            "doctor_id": "VARCHAR(36)",
            "purpose": "VARCHAR(255) NOT NULL DEFAULT 'Наблюдение за состоянием'",
            "schedule_type": "VARCHAR(20) NOT NULL DEFAULT 'once'",
            "interval_days": "INTEGER",
            "scheduled_time": "VARCHAR(5)",
            "timezone": "VARCHAR(80) NOT NULL DEFAULT 'Europe/Moscow'",
            "start_at": "DATETIME",
            "end_at": "DATETIME",
            "reminder_after_minutes": "INTEGER",
            "delivery_channel": "VARCHAR(20) NOT NULL DEFAULT 'max'",
            "last_sent_at": "DATETIME",
            "reminder_sent_at": "DATETIME",
        },
        "questionnaire_responses": {
            "assignment_id": "VARCHAR(36)",
            "version_id": "VARCHAR(36)",
            "answers_json": "TEXT NOT NULL DEFAULT '{}'",
            "source_event_id": "VARCHAR(160)",
        },
        "clinical_alerts": {
            "responsible_doctor_id": "VARCHAR(36)",
        },
        "ai_recommendations": {
            "verification_json": "TEXT NOT NULL DEFAULT '{}'",
        },
    }
    with engine.begin() as connection:
        for table_name, additions in sqlite_columns.items():
            if table_name not in existing_tables:
                continue
            current = {column["name"] for column in inspect(engine).get_columns(table_name)}
            for column_name, declaration in additions.items():
                if column_name not in current:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}"))
