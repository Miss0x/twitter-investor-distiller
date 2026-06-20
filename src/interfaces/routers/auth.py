"""认证 API：/auth/{register, login, refresh, logout, me, invite-code/generate, invite-codes}。

从 web_api.py 抽出，路径与原 @app 完全一致。
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_secure() -> bool:
    """开发环境 HTTP 用 False, 生产环境 HTTPS 用 True."""
    import os as _os  # noqa: PLC0415
    return _os.getenv("ENV", "dev") == "production"


def _is_valid_email(email: str) -> bool:
    """基础邮箱格式验证."""
    return "@" in email and "." in email.split("@")[-1] and len(email) < 256


@router.post("/register")
async def auth_register(payload: dict):
    """用户注册。"""
    from src.admin.auth import hash_password  # noqa: PLC0415
    from src.admin.auth_models import AuthUser, InvitationCode  # noqa: PLC0415
    from src.storage.database import db  # noqa: PLC0415
    email = str(payload.get("email") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    invite_code = str(payload.get("invite_code") or "").strip()
    if not email or not username or not password:
        return {"ok": False, "error": "请填写邮箱、用户名和密码"}
    if not _is_valid_email(email):
        return {"ok": False, "error": "邮箱格式不正确"}
    if len(password) < 6:
        return {"ok": False, "error": "密码至少 6 位"}
    session = db.get_session()
    try:
        code_record = session.query(InvitationCode).filter(
            InvitationCode.code == invite_code,
            InvitationCode.is_used == False,  # noqa: E712
        ).first()
        if not code_record:
            return {"ok": False, "error": "邀请码无效"}
        if session.query(AuthUser).filter(AuthUser.email == email).first():
            return {"ok": False, "error": "邮箱已注册"}
        if session.query(AuthUser).filter(AuthUser.username == username).first():
            return {"ok": False, "error": "用户名已存在"}
        user = AuthUser(email=email, username=username, hashed_password=hash_password(password))
        session.add(user)
        session.flush()
        code_record.is_used = True
        code_record.used_by = user.id
        session.commit()
        return {"ok": True, "message": f"注册成功，欢迎 {username}", "user_id": user.id, "username": user.username}
    finally:
        session.close()


@router.post("/login")
async def auth_login(payload: dict, response: Response):
    """用户登录。返回 Access Token (Cookie) + Refresh Token (Cookie)。"""
    from src.admin.auth import create_access_token, verify_password  # noqa: PLC0415
    from src.admin.auth_models import AuthUser  # noqa: PLC0415
    from src.admin.refresh_token import create_refresh_family  # noqa: PLC0415
    from src.storage.database import db  # noqa: PLC0415
    email = str(payload.get("email") or "").strip()
    password = str(payload.get("password") or "")
    if not email or not password:
        return {"ok": False, "error": "请填写邮箱和密码"}
    session = db.get_session()
    try:
        user = session.query(AuthUser).filter(AuthUser.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            return {"ok": False, "error": "邮箱或密码错误"}
        if not user.is_active:
            return {"ok": False, "error": "账号已被停用"}
        access_token = create_access_token({"sub": user.id, "email": user.email})
        raw_refresh, _ = create_refresh_family(session, user.id, days=7)
        response.set_cookie(
            key="access_token", value=access_token, httponly=True, samesite="lax",
            max_age=1800, secure=_cookie_secure(), path="/",
        )
        response.set_cookie(
            key="refresh_token", value=raw_refresh, httponly=True, samesite="strict",
            max_age=7*86400, secure=_cookie_secure(), path="/auth/refresh",
        )
        return {
            "ok": True, "user_id": user.id, "username": user.username,
            "is_superuser": user.is_superuser,
        }
    finally:
        session.close()


@router.post("/refresh")
async def auth_refresh(request: Request, response: Response):
    """刷新 Access Token。使用 Refresh Token 轮换机制。"""
    from src.admin.auth import create_access_token  # noqa: PLC0415
    from src.admin.refresh_token import rotate_refresh_token, RefreshToken  # noqa: PLC0415
    from src.storage.database import db  # noqa: PLC0415
    import hashlib  # noqa: PLC0415

    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()
    raw_refresh = request.cookies.get("refresh_token", "")
    if not raw_refresh:
        return {"ok": False, "error": "无 Refresh Token"}
    session = db.get_session()
    try:
        result = rotate_refresh_token(session, raw_refresh)
        if result is None:
            return {"ok": False, "error": "Token 无效或已过期，请重新登录"}
        new_raw, _ = result
        record = session.query(RefreshToken).filter(
            RefreshToken.used == False,  # noqa: E712
            RefreshToken.family.in_(
                session.query(RefreshToken.family).filter(
                    RefreshToken.token_hash == _hash_token(raw_refresh)
                ).subquery()
            )
        ).order_by(RefreshToken.created_at.desc()).first()
        user_id = record.user_id if record else None
        if user_id is None:
            return {"ok": False, "error": "会话已失效"}
        access_token = create_access_token({"sub": user_id, "email": ""})
        response.set_cookie(
            key="access_token", value=access_token, httponly=True, samesite="lax",
            max_age=1800, secure=_cookie_secure(), path="/",
        )
        response.set_cookie(
            key="refresh_token", value=new_raw, httponly=True, samesite="strict",
            max_age=7*86400, secure=_cookie_secure(), path="/auth/refresh",
        )
        return {"ok": True}
    finally:
        session.close()


@router.post("/logout")
async def auth_logout(response: Response):
    """登出。"""
    response.delete_cookie("access_token")
    return {"ok": True}


@router.get("/me")
async def auth_me(request: Request):
    """获取当前登录用户信息。"""
    from src.admin.auth import get_current_user  # noqa: PLC0415
    user = get_current_user(request)
    if user is None:
        return {"ok": False, "logged_in": False}
    return {
        "ok": True, "logged_in": True,
        "user_id": user.id, "username": user.username,
        "is_superuser": user.is_superuser,
    }


@router.post("/invite-code/generate")
async def auth_generate_invite_code(request: Request, payload: dict = None):
    """生成邀请码（需要 superuser）。"""
    from src.admin.auth import get_current_user  # noqa: PLC0415
    from src.admin.auth_models import InvitationCode  # noqa: PLC0415
    from src.storage.database import db  # noqa: PLC0415
    user = get_current_user(request)
    if not user or not user.is_superuser:
        return {"ok": False, "error": "需要超级管理员权限"}
    payload = payload or {}
    count = int(payload.get("count", 1))
    count = max(1, min(count, 10))
    session = db.get_session()
    try:
        codes = []
        for _ in range(count):
            import secrets  # noqa: PLC0415
            code = secrets.token_urlsafe(12)
            session.add(InvitationCode(code=code))
            codes.append(code)
        session.commit()
        return {"ok": True, "code": codes[0], "codes": codes, "count": len(codes)}
    finally:
        session.close()


@router.get("/invite-codes")
async def auth_list_invite_codes(request: Request):
    """列出所有邀请码（需要 superuser）。"""
    from src.admin.auth import get_current_user  # noqa: PLC0415
    from src.admin.auth_models import InvitationCode  # noqa: PLC0415
    from src.storage.database import db  # noqa: PLC0415
    user = get_current_user(request)
    if not user or not user.is_superuser:
        return {"ok": False, "error": "需要超级管理员权限"}
    session = db.get_session()
    try:
        codes = session.query(InvitationCode).order_by(InvitationCode.created_at.desc()).all()
        return {"ok": True, "codes": [
            {"code": c.code, "is_used": c.is_used, "used_by": c.used_by,
             "used_at": c.used_at.isoformat() if c.used_at else None}
            for c in codes
        ]}
    finally:
        session.close()
