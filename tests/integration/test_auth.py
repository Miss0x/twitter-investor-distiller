"""集成测试 — 认证流程(注册/登录/me/登出)。

每个测试用独立 user(由 make_user factory 创建),测试间无序依赖。
"""
from __future__ import annotations

import uuid
from tests.integration.conftest import TEST_INVITE_CODE


def _uniq(suffix: str) -> str:
    """生成唯一用户名/邮箱后缀,支持重复运行测试。"""
    return f"{suffix}_{uuid.uuid4().hex[:8]}"


class TestRegister:
    def test_register_success(self, client, seed_invite_code):
        """使用有效邀请码注册应成功。"""
        suffix = _uniq("reg_ok")
        r = client.post("/auth/register", json={
            "email": f"{suffix}@test.com",
            "username": f"u_{suffix}",
            "password": "NewPass123",
            "invite_code": TEST_INVITE_CODE,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "注册成功" in body.get("message", "")

    def test_register_missing_fields(self, client):
        """缺少字段时应返回提示。"""
        r = client.post("/auth/register", json={"email": "a@b.com"})
        body = r.json()
        assert body["ok"] is False
        assert body.get("error")

    def test_register_weak_password(self, client):
        """弱密码应被拒绝。"""
        suffix = _uniq("weak")
        r = client.post("/auth/register", json={
            "email": f"{suffix}@test.com",
            "username": f"u_{suffix}",
            "password": "123",
            "invite_code": TEST_INVITE_CODE,
        })
        body = r.json()
        assert body["ok"] is False
        assert "密码" in body.get("error", "")

    def test_register_invalid_invite(self, client):
        """无效邀请码应被拒绝。"""
        suffix = _uniq("bad_inv")
        r = client.post("/auth/register", json={
            "email": f"{suffix}@test.com",
            "username": f"u_{suffix}",
            "password": "Pass12345",
            "invite_code": "INVALID-CODE-DOES-NOT-EXIST",
        })
        body = r.json()
        assert body["ok"] is False
        assert "邀请码无效" in body.get("error", "")


class TestLogin:
    def test_login_success(self, make_user):
        """已注册用户登录应成功。"""
        auth_client = make_user("login_ok")
        r = auth_client.get("/auth/me")
        body = r.json()
        assert body["logged_in"] is True
        assert body["username"].startswith("u_login_ok")

    def test_login_wrong_password(self, make_user):
        """错误密码应返回统一错误。"""
        auth_client = make_user("login_wrong_pwd")
        # 登出后再用错误密码登录
        auth_client.post("/auth/logout")
        r = auth_client.post("/auth/login", json={
            "email": "u-login_wrong_pwd@test.com",
            "password": "WrongPass123",
        })
        body = r.json()
        assert body["ok"] is False
        assert "邮箱或密码错误" in body.get("error", "")

    def test_login_nonexistent_user(self, client):
        """不存在的用户应返回统一错误(不区分不存在 vs 密码错)。"""
        r = client.post("/auth/login", json={
            "email": "nobody-nonexistent-xyz@test.com",
            "password": "SomePass123",
        })
        body = r.json()
        assert body["ok"] is False
        assert "邮箱或密码错误" in body.get("error", "")


class TestMe:
    def test_me_logged_in(self, make_user):
        """已登录时 /auth/me 应返回用户信息。"""
        auth_client = make_user("me_ok")
        r = auth_client.get("/auth/me")
        body = r.json()
        assert body["logged_in"] is True
        assert body["username"].startswith("u_me_ok")

    def test_me_anonymous(self, client):
        """未登录时 /auth/me 应返回 logged_in=False。"""
        r = client.get("/auth/me")
        body = r.json()
        assert body["logged_in"] is False


class TestLogout:
    def test_logout_clears_session(self, make_user):
        """登出后 /auth/me 应返回 logged_in=False。"""
        auth_client = make_user("logout_ok")

        # 登出前确认已登录
        r = auth_client.get("/auth/me")
        assert r.json()["logged_in"] is True

        # 执行登出
        r = auth_client.post("/auth/logout")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # 登出后确认未登录
        r = auth_client.get("/auth/me")
        assert r.json()["logged_in"] is False


class TestInviteCodeGenerate:
    def test_generate_invite_code_as_superuser(self, make_user):
        """超级管理员生成邀请码 — 回归 user.id → _user.id 真 bug。

        历史 bug: web_api.py:610 引用未定义的 `user` 而非 `_user`,
        每次调用都会抛 NameError。修复后必须返回有效邀请码。
        """
        import secrets

        auth_client = make_user("super_invite")
        # 该用户是注册时的第一个 → superuser（项目约定，见 auth_models）
        # 但 make_user 默认非超管，我们需要直接拿一个超管 token
        from src.admin.auth import create_access_token
        from src.storage.database import db
        from src.admin.auth_models import AuthUser

        session = db.get_session()
        try:
            admin = session.query(AuthUser).filter(AuthUser.is_superuser == True).first()  # noqa: E712
            if admin is None:
                # 项目里若没有 superuser，跳过此测试（环境前置）
                return
            token = create_access_token({"sub": admin.id, "email": admin.email})
        finally:
            session.close()

        r = auth_client.post(
            "/auth/invite-code/generate",
            cookies={"access_token": token},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body.get("code")
        # 必须符合 secrets.token_urlsafe(12) 格式
        assert len(body["code"]) >= 16
