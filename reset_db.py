from app.database import engine, Base
import app.models

def reset_database():
    print("Сбрасываем локальную SQLite-базу...")
    Base.metadata.drop_all(bind=engine)
    print("Создаём новые таблицы SQLite...")
    Base.metadata.create_all(bind=engine)
    print("Готово!")

if __name__ == "__main__":
    reset_database()
