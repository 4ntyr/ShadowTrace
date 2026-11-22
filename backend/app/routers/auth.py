from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..security import (
    auth_limiter,
    burn_hash_time,
    clear_session,
    current_user,
    current_user_optional,
    hash_password,
    issue_session,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class PasswordConfirmIn(BaseModel):
    password: str = Field(max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "is_admin": u.is_admin}


@router.post("/register", status_code=201, dependencies=[Depends(auth_limiter)])
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    if not get_settings().allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is disabled")
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    u = User(email=email, display_name=body.display_name.strip(), password_hash=hash_password(body.password))
    db.add(u)
    db.commit()
    issue_session(response, u)
    return user_out(u)


@router.post("/login", dependencies=[Depends(auth_limiter)])
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.lower()))
    if u is None:
        burn_hash_time(body.password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not verify_password(body.password, u.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    issue_session(response, u)
    return user_out(u)


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_session(response)


@router.get("/me")
def me(user: User | None = Depends(current_user_optional)):
    return {"user": user_out(user) if user else None, "registration_open": get_settings().allow_registration}


@router.post("/password", status_code=204, dependencies=[Depends(auth_limiter)])
def change_password(
    body: PasswordChangeIn, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    # Truncate to whole seconds: JWT iat has second resolution, so the new session must not predate it.
    user.password_changed_at = datetime.now(timezone.utc).replace(microsecond=0)
    db.commit()
    issue_session(response, user)  # keep this session, invalidate all others


@router.post("/delete-account", status_code=204, dependencies=[Depends(auth_limiter)])
def delete_account(
    body: PasswordConfirmIn, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect")
    db.delete(user)
    db.commit()
    clear_session(response)
