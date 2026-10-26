from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select

from app.database import Base, SessionLocal, engine, ensure_schema
from app.max_bot import max_api_request, process_update, request_next_consent
from app.models import MaxUserBinding
from app.scheduler import dispatch_due_assignments
from app.seed import seed_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("max-bot")


def subscription_count(payload: dict[str, Any]) -> int:
    subscriptions = payload.get("subscriptions", [])
    return len(subscriptions) if isinstance(subscriptions, list) else 0


def run() -> None:
    ensure_schema()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)

    subscriptions = max_api_request("GET", "/subscriptions")
    if subscription_count(subscriptions):
        raise RuntimeError(
            "У бота уже настроен Webhook. Long Polling нельзя использовать одновременно с Webhook."
        )

    identity = max_api_request("GET", "/me")
    visible_name = identity.get("name") or identity.get("username") or "MAX bot"
    logger.info("Бот %s подключён. Локальный Long Polling запущен.", visible_name)
    with SessionLocal() as db:
        pending_bindings = db.scalars(
            select(MaxUserBinding).where(MaxUserBinding.status == "pending_legal_setup")
        ).all()
        for binding in pending_bindings:
            request_next_consent(db, binding)
        db.commit()
    if pending_bindings:
        logger.info("Возобновлено подключений после публикации согласий: %s", len(pending_bindings))
    marker: int | None = None

    while True:
        try:
            params: dict[str, Any] = {"limit": 100, "timeout": 30}
            if marker is not None:
                params["marker"] = marker
            payload = max_api_request("GET", "/updates", params=params, timeout=45.0)
            for update in payload.get("updates", []):
                with SessionLocal() as db:
                    process_update(db, update)
            if payload.get("marker") is not None:
                marker = int(payload["marker"])
            with SessionLocal() as db:
                dispatch_due_assignments(db)
        except KeyboardInterrupt:
            logger.info("Бот остановлен.")
            return
        except Exception as error:
            logger.error("Ошибка MAX: %s", error)
            time.sleep(5)


if __name__ == "__main__":
    run()
