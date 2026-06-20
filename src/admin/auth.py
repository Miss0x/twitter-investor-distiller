"""Authentication service — JWT, password hashing, permission checking."""

from __future__ import annotations

import hashlib
import os
import secrets as _secrets
from datetime import datetime, timedelta, timezone

import bcrypt

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from src.admin.auth_models import AuthUser

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == "dev-secret-change-in-production":
    import sys
    print("⚠️  警告: JWT_SECRET_KEY 未设置或使用默认值, 生产环境请设置环境变量 JWT_SECRET_KEY", file=sys.stderr)
    SECRET_KEY = SECRET_KEY or "dev-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码。兼容旧 SHA-256 哈希和新 bcrypt 哈希。

    旧格式：40 字符 hex（SHA-256）
    新格式：以 $2b$ 开头（bcrypt）
    """
    if hashed.startswith("$2b$"):
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    # 旧 SHA-256 格式验证（兼容迁移期）
    old_salt = os.getenv("OLD_PASSWORD_SALT", "")
    old_hash = hashlib.sha256((old_salt + plain).encode()).hexdigest()
    return _secrets.compare_digest(old_hash, hashed)


def hash_password(plain: str) -> str:
    """使用 bcrypt 哈希密码（work_factor=12）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request) -> AuthUser | None:
    """Try to get current user from JWT. Returns None if no valid token (public mode)."""
    token = request.cookies.get("access_token") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        user_id = int(sub)
    except (JWTError, ValueError):
        return None

    from src.storage.database import db as database

    session = database.get_session()
    try:
        return session.query(AuthUser).filter(AuthUser.id == user_id).first()
    finally:
        session.close()


def require_admin(user: AuthUser | None = Depends(get_current_user)) -> AuthUser:
    """Require authenticated admin/superuser."""
    if user is None:
        raise HTTPException(status_code=401, detail="请先登录")
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def check_permission(permission_name: str):
    """FastAPI dependency factory: require specific permission."""

    def _check(user: AuthUser | None = Depends(get_current_user)) -> AuthUser:
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
