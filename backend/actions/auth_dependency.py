from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from actions.auth_action import decode_access_token
from db.database import SessionLocal
from db.models import Employee


def _normalize_role(role: str | None) -> str:
    r = (role or "").strip().lower()
    if r in {"it", "itteam", "it-team", "it team"}:
        return "it_team"
    if r in {"hr", "hr_team", "hr-team", "hr team"}:
        return "employee"
    if r in {"employee", "manager", "it_team", "admin"}:
        return r
    return "employee"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0].strip().lower(), parts[1].strip()
    if scheme != "bearer" or not token:
        return None
    return token


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Employee:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer token")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(Employee).filter(Employee.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    user.role = _normalize_role(getattr(user, "role", None))

    return user


def require_roles(*roles: str):
    allowed = {r.lower() for r in roles}

    def _dep(user: Annotated[Employee, Depends(get_current_user)]) -> Employee:
        if (user.role or "").lower() not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return _dep

