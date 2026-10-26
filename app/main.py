import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.database import Base, SessionLocal, check_connection, engine, ensure_schema
from app.integration_api import router as integration_router
from app.seed import seed_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    yield


app = FastAPI(title="Клинический компас API", version="0.2.0", lifespan=lifespan)
origins = [
    value.strip()
    for value in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3125,http://127.0.0.1:3125",
    ).split(",")
    if value.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(integration_router)


@app.get("/")
def home():
    return {"service": "clinical-compass-api", "version": "0.2.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"api": "ok"}


@app.get("/health/db")
def database_health():
    try:
        check_connection()
        return {"database": "connected"}
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Ошибка подключения к базе данных: {type(error).__name__}",
        ) from error
