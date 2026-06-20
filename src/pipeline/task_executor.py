"""
流水线任务执行器 —— 项目核心执行引擎
=======================================================

6 种任务类型的执行逻辑已拆分到:
  exec_filter.py   → _filter_tweets
  exec_analyze.py  → _analyze_tweet + _save_analyzed + _enrich_price_context
  exec_fetch.py    → _fetch_price + _fetch_crypto + _fetch_polygon
  exec_portrait.py → _generate_portrait

本文件保留：全局状态、调度入口、共享工具函数。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import yaml as _yaml

from src.storage.database import db
from src.storage.models import PipelineTask


# ═══════════════════════════════════════════════════════════════════════
# 全局状态 —— 单线程执行器状态管理
# ═══════════════════════════════════════════════════════════════════════

_executor_lock = threading.Lock()
_current_task_id: int | None = None


def _clean_analysis() -> dict:
    from src.storage.alias_repository import AliasRepository
    alias = AliasRepository.get_map()
    cleaned = 0
    for fp in sorted(Path("data/pipeline").glob("*_analyzed.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        updated = False
        for item in data:
            stocks = item.get("mentioned_stocks", [])
            if stocks:
                mapped = [alias.get(s.strip(), s.strip()) for s in stocks]
                if mapped != stocks:
                    item["mentioned_stocks"] = mapped
                    item["_cleaned"] = True
                    updated = True
                    cleaned += 1
        if updated:
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return {"ok": True, "cleaned": cleaned}


# ═══════════════════════════════════════════════════════════════════════
# 进度与状态查询
# ═══════════════════════════════════════════════════════════════════════

_progress: dict = {"total": 0, "done": 0, "msg": ""}


def get_progress() -> dict:
    return dict(_progress)


def is_running() -> bool:
    return _current_task_id is not None


# ═══════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════

with open(Path(__file__).parent.parent.parent / "config" / "pipeline.yaml", encoding="utf-8") as _f:
    _PIPELINE_CFG = _yaml.safe_load(_f) or {}
POLYGON_KEY = _PIPELINE_CFG.get("api", {}).get("polygon_key", "")
PRICES_PATH = Path("data/prices.json")
CRYPTO_PRICES_PATH = Path("data/crypto_prices.json")


# ── Import executor functions (must be after shared state above) ──

# ═══════════════════════════════════════════════════════════════════════
# 任务调度入口
# ═══════════════════════════════════════════════════════════════════════

def execute_tasks(task_ids: list[int]) -> None:
    """按指定 ID 列表顺序逐条执行流水线任务。"""
    global _current_task_id, _progress
    if not _executor_lock.acquire(blocking=False):
        return
    # 懒加载 executor 函数（避免 module 顶层 import 拉起 LLM 依赖链）
    from .exec_filter import _filter_tweets
    from .exec_analyze import _analyze_tweet
    from .exec_fetch import _fetch_price, _fetch_crypto
    from .exec_portrait import _generate_portrait
    try:
        session = db.get_session()
        try:
            tasks = session.query(PipelineTask).filter(
                PipelineTask.id.in_(task_ids),
                PipelineTask.status.in_(["pending", "failed"]),
            ).order_by(PipelineTask.id).all()
        finally:
            session.close()
        if not tasks:
            return
        _progress = {"total": len(tasks), "done": 0, "msg": "准备就绪"}
        for t in tasks:
            _current_task_id = t.id
            _progress["msg"] = f"执行 {t.task_type} #{t.id}..."
            session = db.get_session()
            try:
                record = session.query(PipelineTask).get(t.id)
                if not record:
                    continue
                record.status = "running"
                session.commit()
            finally:
                session.close()
            payload = json.loads(t.payload) if t.payload else {}
            try:
                if t.task_type == "filter":
                    result = _filter_tweets(payload)
                elif t.task_type == "fetch_price":
                    result = _fetch_price(payload["ticker"])
                elif t.task_type == "fetch_crypto":
                    result = _fetch_crypto(payload["ticker"])
                elif t.task_type == "analyze":
                    result = _analyze_tweet(payload)
                elif t.task_type == "portrait":
                    result = _generate_portrait(payload["username"])
                elif t.task_type == "clean":
                    result = _clean_analysis()
                elif t.task_type.startswith("governance_"):
                    result = _dispatch_governance_task(t.task_type, payload)
                else:
                    result = {"error": f"未知任务类型: {t.task_type}"}
            except Exception as e:
                result = {"error": str(e)}
            session = db.get_session()
            try:
                record = session.query(PipelineTask).get(t.id)
                if record:
                    record.status = "done" if result.get("ok") else "failed"
                    if result.get("error"):
                        existing = record.error_msg or ""
                        record.error_msg = existing + f" | {result['error']}"
                    session.commit()
            finally:
                session.close()
            _progress["done"] += 1
            _current_task_id = None
        _progress["msg"] = "全部完成"
    finally:
        _current_task_id = None
        _executor_lock.release()
        # 清空价格/基本面缓存（仅当模块已加载时）
        try:
            from .exec_analyze import _prices_cache, _fundamentals_cache
            _prices_cache["data"] = {}
            _prices_cache["ts"] = 0
            _fundamentals_cache["data"] = {}
            _fundamentals_cache["ts"] = 0
        except ImportError:
            pass


# ═══════════════════════════════════════════════════════════════════════
# 治理任务分发
# ═══════════════════════════════════════════════════════════════════════

_GOVERNANCE_TASKS = {
    "governance_data_gaps", "governance_quality_gate", "governance_panel_review",
    "governance_llm_review", "governance_debate", "governance_risk_scan",
    "governance_package_builder", "governance_publish_gate",
    # 兼容别名（测试 / 调用方可能使用简短名称）
    "governance_candidate", "governance_quality", "governance_risk",
    "governance_panel", "governance_publish",
    "governance_report", "governance_run",
}


def _dispatch_governance_task(task_type: str, payload: dict) -> dict:
    """分发治理任务到实际的 governance runner。

    对于 ``governance_run``：从 payload 中提取 ``candidate`` (SignalCandidate)
    和可选的 ``repo_base_dir``，执行完整的 governance 链，返回::

        {"ok": True, "publish_status": ..., "package_path": ...}

    对于其他已识别类型：空 payload 时 fail closed，返回 ``{"error": ...}``。
    未知类型返回 ``{"error": "未知治理任务: ...}"``。
    """
    if task_type not in _GOVERNANCE_TASKS:
        return {"error": f"未知治理任务: {task_type}"}

    # governance_run：执行完整治理链
    if task_type == "governance_run":
        candidate = payload.get("candidate")
        if candidate is None:
            return {"error": "governance_run 需要 payload.candidate (SignalCandidate)"}
        from src.governance.runner import run_governance_for_candidate
        from src.governance.repository import GovernanceRepository

        repo_base_dir = payload.get("repo_base_dir")
        repo = GovernanceRepository(base_dir=repo_base_dir) if repo_base_dir else None
        result = run_governance_for_candidate(candidate, repo=repo)
        if result.status == "failed":
            return {"ok": False, "error": result.error or "治理链执行失败"}
        return {
            "ok": True,
            "publish_status": result.publish_status,
            "package_path": result.package_path or "",
            "report_path": result.report_path or "",
        }

    # 其他治理阶段：空 payload 时 fail closed
    if not payload:
        return {"error": f"{task_type} 需要非空 payload"}

    # 单阶段执行（预留：目前只有 governance_run 有完整实现）
    stage = task_type.replace("governance_", "")
    return {"error": f"单阶段治理任务 {stage} 尚未实现独立分发，请使用 governance_run"}
