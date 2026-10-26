import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Cookie, Depends, HTTPException, Response
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

password_hash = PasswordHash.recommended()
SECRET = os.getenv("JWT_SECRET", "replace-this-development-secret-at-least-32-bytes")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def create_session(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user.id, "role": user.role, "iat": now, "exp": now + timedelta(hours=12)}, SECRET, algorithm=ALGORITHM)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "cc_session",
        token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "0") == "1",
        samesite=os.getenv("COOKIE_SAMESITE", "lax"),
        max_age=43200,
        path="/",
    )


def current_user(cc_session: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    if not cc_session:
        raise HTTPException(status_code=401, detail="Требуется вход")
    try:
        payload = jwt.decode(cc_session, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=401, detail="Сессия недействительна") from error
    user = db.scalar(select(User).where(User.id == payload.get("sub")))
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user


def require_doctor(user: User = Depends(current_user)) -> User:
    if user.role not in {"doctor", "admin"}:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return user