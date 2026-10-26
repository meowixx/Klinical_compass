from app import models  # noqa: F401
from app.database import Base, SessionLocal, engine, ensure_schema
from app.seed import seed_database


def main():
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    with SessionLocal() as db:
        seed_database(db)
    print("Таблицы Клинического компаса созданы, тестовые данные добавлены.")


if __name__ == "__main__":
    main()
