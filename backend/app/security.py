"""Password hashing, session tokens (JWT in an httpOnly cookie) and auth dependencies."""

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import User

COOKIE = "st_session"
ALGO = "HS256"


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


# Constant-time-ish rejection for unknown emails (avoid user enumeration via timing).
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt(rounds=12)).decode()


def burn_hash_time(pw: str) -> None:
    verify_password(pw, _DUMMY_HASH)


def issue_session(response: Response, user: User) -> None:
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=s.session_hours)
    token = jwt.encode({"sub": str(user.id), "iat": now, "exp": exp}, s.secret_key, algorithm=ALGO)
    response.set_cookie(
        COOKIE,
        token,
        max_age=s.session_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGO], options={"require": ["sub", "iat", "exp"]})
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, ValueError):
        return None
    if user is None:
        return None
    changed = user.password_changed_at
    if changed is not None:
        if changed.tzinfo is None:
            changed = changed.replace(tzinfo=timezone.utc)
        if payload["iat"] < int(changed.timestamp()):
            return None  # session predates a password change
    return user


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return user


class RateLimiter:
    """Tiny in-process sliding-window limiter (per client IP) for auth endpoints."""

    def __init__(self, limit: int, window_s: int):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")
        q.append(now)


auth_limiter = RateLimiter(limit=10, window_s=60)
