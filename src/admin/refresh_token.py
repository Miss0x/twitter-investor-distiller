"""Refresh Token rotation — Auth0/IETF best practice.

Implements token rotation + reuse detection + family revocation.
Reference: https://uguraslim.com/blog/fastapi-jwt-rotation/
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Session


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _RTBase(DeclarativeBase):
    pass


class RefreshToken(_RTBase):
    __tablename__ = "auth_refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    family = Column(String(36), nullable=False, index=True)
    used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, _hash_token(raw)


def create_refresh_family(session: Session, user_id: int, days: int = 7) -> tuple[str, RefreshToken]:
    raw, token_hash = generate_refresh_token()
    family = uuid4().hex
    expires = _utcnow() + timedelta(days=days)
    record = RefreshToken(
        user_id=user_id, token_hash=token_hash,
        family=family, expires_at=expires,
    )
    session.add(record)
    session.commit()
    return raw, record


def rotate_refresh_token(session: Session, raw_old_refresh: str) -> tuple[str, str] | None:
    old_hash = _hash_token(raw_old_refresh)
    record = session.query(RefreshToken).filter(
        RefreshToken.token_hash == old_hash
    ).with_for_update().first()

    if record is None:
        return None

    if record.used:
        session.query(RefreshToken).filter(
            RefreshToken.family == record.family
        ).update({"used": True})
        session.commit()
        return None

    if record.expires_at < _utcnow():
        return None

    record.used = True
    new_raw, new_hash = generate_refresh_token()
    new_record = RefreshToken(
        user_id=record.user_id, token_hash=new_hash,
        family=record.family, expires_at=_utcnow() + timedelta(days=7),
    )
    session.add(new_record)
    session.commit()
    return new_raw, _hash_token(new_raw)


def revoke_user_tokens(session: Session, user_id: int) -> int:
    count = session.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.used == False,  # noqa: E712
        RefreshToken.expires_at > _utcnow(),
    ).update({"used": True})
    session.commit()
    return count


def cleanup_expired_tokens(session: Session) -> int:
    count = session.query(RefreshToken).filter(
        RefreshToken.expires_at < _utcnow()
    ).delete()
    session.commit()
    return count
