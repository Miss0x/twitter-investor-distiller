"""Authentication service — JWT, password hashing, permission checking."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from src.admin.auth_models import User

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    request: Request,
    db: Session = Depends(lambda: None),
) -> User | None:
    """Try to get current user from JWT. Returns None if no valid token (public mode)."""
    token = request.cookies.get("access_token") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int | None = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    from src.storage.database import db as database

    session = database.get_session()
    try:
        return session.query(User).filter(User.id == user_id).first()
    finally:
        session.close()


def require_admin(user: User | None = Depends(get_current_user)) -> User:
    """Require authenticated admin/superuser."""
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def check_permission(permission_name: str):
    """FastAPI dependency factory: require specific permission."""

    def _check(user: User | None = Depends(get_current_user)) -> User:
        if user is None:
            raise HTTPException(status_code=401, detail="请先登录")
        if user.is_superuser:
            return user
        for role in user.roles:
            for perm in role.permissions:
                if perm.name == permission_name:
                    return user
        raise HTTPException(status_code=403, detail=f"需要权限: {permission_name}")

    return _check
