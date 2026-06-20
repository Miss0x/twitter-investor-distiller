"""集成测试 — 通用 fixtures。

设计:
    - 每个测试函数的 make_user fixture 创建独立 user + 独立 tenant 目录
    - 测试结束后 teardown 清理 user 记录和 tenant 目录,杜绝测试间污染
    - 使用 dependency_overrides 避免真实的 IP 限流和外部依赖
    - 不依赖测试执行顺序(可与 pytest-randomly 配合)
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.interfaces.web_api import app
from src.storage.database import db

TEST_INVITE_CODE = "TEST-INTEG-001"
TEST_PASSWORD = "Password1"
TENANTS_DIR = Path("data/tenants")


# ── 禁用 IP 限流(测试环境需要多次请求) ──
@pytest.fixture(autouse=True)
def _bypass_rate_limit():
    """自动禁用速率限制(全局限流 + 认证限流),确保测试不被限流阻塞。"""
    import src.interfaces.web_api as api
    api._auth_rate_limit.clear()
    api._rate_buckets.clear()
    yield
    api._auth_rate_limit.clear()
    api._rate_buckets.clear()


# ── TestClient ──
@pytest.fixture
def client():
    """FastAPI TestClient 实例(无登录态)。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seed_invite_code():
    """确保测试邀请码存在且可用。"""
    from src.admin.auth_models import InvitationCode as IC
    session = db.get_session()
    try:
        existing = session.query(IC).filter(IC.code == TEST_INVITE_CODE).first()
        if existing:
            existing.is_used = False
            existing.used_at = None
            existing.used_by = None
        else:
            session.add(IC(code=TEST_INVITE_CODE))
        session.commit()
    finally:
        session.close()


# ── User Factory(关键:每个测试独立 user) ──
@pytest.fixture
def make_user(client, seed_invite_code):
    """Factory fixture: 创建独立 user + 独立 tenant 目录,自动 teardown。

    用法:
        def test_xxx(make_user):
            auth_client = make_user("alice")
            r = auth_client.get("/auth/me")
            ...

    Returns:
        已登录的 client(JWT cookie 已注入)
    """
    from src.admin.auth_models import AuthUser, InvitationCode as IC

    created = []  # [(user_id, email)]

    def _make(suffix: str | None = None) -> TestClient:
        s = suffix or uuid.uuid4().hex[:8]
        email = f"u-{s}@test.com"
        username = f"u_{s}"

        # 注册
        r = client.post("/auth/register", json={
            "email": email,
            "username": username,
            "password": TEST_PASSWORD,
            "invite_code": TEST_INVITE_CODE,
        })
        assert r.status_code == 200, f"注册失败: {r.text}"
        assert r.json().get("ok") is True, f"注册返回错误: {r.json()}"

        # 登录(注入 cookie)
        r = client.post("/auth/login", json={
            "email": email,
            "password": TEST_PASSWORD,
        })
        assert r.status_code == 200, f"登录失败: {r.text}"
        assert r.json().get("ok") is True, f"登录返回错误: {r.json()}"

        # 记录 user_id 用于 teardown
        session = db.get_session()
        try:
            user = session.query(AuthUser).filter(AuthUser.email == email).first()
            if user:
                created.append((user.id, email))
        finally:
            session.close()

        return client

    yield _make

    # ── Teardown: 清理 user 记录、关联表、tenant 目录 ──
    if not created:
        return
    session = db.get_session()
    try:
        for user_id, _ in created:
            # 1. 解绑邀请码的 used_by 外键
            session.query(IC).filter(IC.used_by == user_id).update(
                {"used_by": None, "is_used": False, "used_at": None},
                synchronize_session=False,
            )
            # 2. 删除 refresh_tokens(单独的 base, 不在 AuthUser Base.metadata 里)
            from src.admin.refresh_token import RefreshToken
            session.query(RefreshToken).filter(RefreshToken.user_id == user_id).delete(
                synchronize_session=False,
            )
            # 3. 删除 DB user 记录
            user = session.query(AuthUser).filter(AuthUser.id == user_id).first()
            if user:
                session.delete(user)
            # 4. 清理 tenant 目录
            tenant_dir = TENANTS_DIR / str(user_id)
            if tenant_dir.exists():
                shutil.rmtree(tenant_dir, ignore_errors=True)
        session.commit()
    finally:
        session.close()