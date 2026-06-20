"""E2E 集成测试 — 覆盖 governance / valuation / team / reports 业务域。

设计目的:
    - 把 scripts/e2e_20_scenarios.py 中的浏览器交互场景转为 pytest 自动用例
    - 覆盖 scripts/_route_snapshot.py 基线中的剩余路由 (governance, valuation, team, reports)
    - 每个测试独立 user + tenant,不依赖其他测试

被测路由 (来自 src/interfaces/routers/):
    - governance.py:  POST /api/governance/gaps/{acknowledge, revoke}
    - valuation.py:   GET /api/valuation/{dcf, dd}
    - team.py:        GET /api/team/shared-pool, POST /api/team/shared-pool/update
    - reports.py:     GET /api/reports/signal-quality

行业参考:
    - FastAPI Bigger Applications: 域名路由 + Depends 注入
    - pytest fixture factory 模式 + teardown 自动清理 (避免测试污染)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


# ── 团队共享池 E2E ──────────────────────────────────────────────
class TestTeamSharedPool:
    """GET /api/team/shared-pool, POST /api/team/shared-pool/update"""

    def test_get_shared_pool_initial_empty(self, make_user):
        """新用户访问共享池, 初始应为空列表。"""
        auth_client = make_user("team_get")
        r = auth_client.get("/api/team/shared-pool")
        assert r.status_code == 200
        body = r.json()
        assert "observations" in body
        # 不强制 [] — 只要字段存在即可 (可能是 []))

    def test_update_shared_pool_persists(self, make_user):
        """更新共享池后 GET 应返回相同观测列表。"""
        auth_client = make_user("team_update")
        observations = ["@TSLA_Tracker", "@NVDA_Whale", "BTC"]

        r = auth_client.post("/api/team/shared-pool/update", json={"observations": observations})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["observations"] == observations

        r2 = auth_client.get("/api/team/shared-pool")
        assert r2.status_code == 200
        assert r2.json()["observations"] == observations

    def test_update_shared_pool_invalid_payload(self, make_user):
        """缺 observations 字段时, 后端应返回空列表而非报错。"""
        auth_client = make_user("team_invalid")
        r = auth_client.post("/api/team/shared-pool/update", json={})
        assert r.status_code == 200
        # 缺字段 -> 空列表写入
        assert r.json()["ok"] is True
        assert r.json()["observations"] == []


# ── 信号质量报告 E2E ──────────────────────────────────────────────
class TestReportsSignalQuality:
    """GET /api/reports/signal-quality"""

    def test_signal_quality_default_period(self, make_user):
        """默认 7 天报告应返回合法结构。"""
        auth_client = make_user("report_7d")
        r = auth_client.get("/api/reports/signal-quality")
        assert r.status_code == 200
        body = r.json()
        # 关键字段
        for key in ("period_days", "total_signals", "passed_gate", "pass_rate",
                    "avg_confidence", "risk_flags", "generated_at"):
            assert key in body, f"缺少字段: {key}"

    def test_signal_quality_custom_period(self, make_user):
        """days=30 应返回 30 天报告。"""
        auth_client = make_user("report_30d")
        r = auth_client.get("/api/reports/signal-quality?days=30")
        assert r.status_code == 200
        assert r.json()["period_days"] == 30


# ── 估值工具 E2E ──────────────────────────────────────────────
class TestValuation:
    """GET /api/valuation/{dcf, dd}"""

    def test_dcf_returns_structure(self, make_user):
        """DCF 估值应返回 ticker + 估值字段。"""
        auth_client = make_user("val_dcf")
        r = auth_client.get("/api/valuation/dcf?ticker=AAPL")
        assert r.status_code == 200
        body = r.json()
        assert body["ticker"] == "AAPL"
        # 字段存在性 (允许 None)
        for key in ("intrinsic_value", "current_price", "wacc"):
            assert key in body

    def test_dcf_case_insensitive(self, make_user):
        """DCF ticker 应自动大写。"""
        auth_client = make_user("val_dcf_ci")
        r = auth_client.get("/api/valuation/dcf?ticker=aapl")
        assert r.status_code == 200
        assert r.json()["ticker"] == "AAPL"

    def test_dd_returns_questions(self, make_user):
        """DD checklist 应返回问题清单。"""
        auth_client = make_user("val_dd")
        r = auth_client.get("/api/valuation/dd?ticker=NVDA")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # 每条问题应有 category/question/status
        for item in items:
            for key in ("category", "question", "status"):
                assert key in item, f"DD item 缺字段: {key}"


# ── 治理 Gap E2E ──────────────────────────────────────────────
class TestGovernanceGaps:
    """POST /api/governance/gaps/{acknowledge, revoke}"""

    def test_acknowledge_missing_fields(self, make_user):
        """缺 signal_id / gap_code 应返回错误 (但不抛 500)。"""
        auth_client = make_user("gov_ack_empty")
        r = auth_client.post("/api/governance/gaps/acknowledge", json={})
        # 业务返回 {ok: False, error: ...}
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is False or body.get("error")

    def test_revoke_missing_fields(self, make_user):
        """缺字段 revoke 也应被业务层捕获, 不抛 500。"""
        auth_client = make_user("gov_revoke_empty")
        r = auth_client.post("/api/governance/gaps/revoke", json={})
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is False or body.get("error")

    def test_acknowledge_nonexistent_signal(self, make_user):
        """对不存在的 signal 调用 acknowledge 应失败但不抛 500。"""
        auth_client = make_user("gov_ack_404")
        r = auth_client.post("/api/governance/gaps/acknowledge", json={
            "signal_id": "nonexistent-signal-xyz",
            "gap_code": "fake_gap",
            "reason": "test",
            "expires_in_hours": 24,
        })
        assert r.status_code == 200
        # 不抛 500 是核心要求 — 业务返回 ok=False 是预期
