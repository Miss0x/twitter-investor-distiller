"""卡片模块化 API：/cards/{meta, {name}, {name}/action}。

从 web_api.py 抽出，路径与原 @app.get/@app.post 完全一致。
依赖：
    - src.cards（CARDS、get_card）
    - src.cards.config_center_card._current_request（卡片读取当前请求）
    - src.cards.card_schema.validate_card_data
    - src.api.schemas（CardMetaItem、CardRenderResponse、CardActionResponse）
    - handlers_insights / handlers_exec / handlers_data（动作分发）
"""
from __future__ import annotations

import time as _time

from fastapi import APIRouter, HTTPException, Request

from src.api.schemas import CardActionResponse, CardMetaItem, CardRenderResponse
from src.cards import CARDS, get_card
from src.interfaces.handlers_data import _handle_asset_alias, _handle_portrait_generate, _handle_user_manage
from src.interfaces.handlers_exec import _handle_fetch_control, _handle_pipeline_action, _handle_script_run
from src.interfaces.handlers_insights import _handle_portfolio_analysis, _handle_role_picker

router = APIRouter(prefix="/cards", tags=["cards"])

# 卡片缓存：{name: ((html, data), expire_timestamp)}
_card_cache: dict[str, tuple[tuple[str, dict], float]] = {}
_CACHE_TTL = 10  # 卡片缓存 TTL (秒), 减少重复 Jinja2 渲染


def invalidate_card_cache(*names: str) -> None:
    """清除指定名称的卡片缓存（供 governance 等外部模块调用）。"""
    for name in names:
        _card_cache.pop(name, None)


def _get_cached_card_html(name: str) -> tuple[str, dict] | None:
    """从服务端缓存获取卡片 HTML 和 data。

    Args:
        name: 卡片名称

    Returns:
        (html, data) 元组，None 表示未命中或已过期
    """
    now = _time.time()
    if name in _card_cache:
        (html, data), expire = _card_cache[name]
        if now < expire:
            return (html, data)
    return None


def _set_cached_card_html(name: str, html: str, data: dict) -> None:
    """设置卡片缓存（HTML + data 一起缓存）。"""
    _card_cache[name] = ((html, data), _time.time() + _CACHE_TTL)


async def _render_card_data(name: str):
    """渲染卡片（带缓存 + dataclass schema 校验）。"""
    cached = _get_cached_card_html(name)
    if cached is not None:
        html, data = cached
        return {"html": html, "data": data, "error": None}

    card = get_card(name)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Card '{name}' not found")

    try:
        data = card.get_data()       # 获取卡片数据
        # ── 规则五：dataclass schema 校验 ──
        from src.cards.card_schema import validate_card_data  # noqa: PLC0415
        data, schema_warning = validate_card_data(name, data)
        html = card.render(data)     # 渲染为 HTML
        _set_cached_card_html(name, html, data)
        return {"html": html, "data": data, "error": None}
    except Exception as e:
        return {
            "html": (
                f'<div class="card"><div class="flex">'
                f'<div class="status-dot err"></div>'
                f'<span class="text-secondary">{name}: '
                f'{str(e).replace("<","&lt;").replace(">","&gt;")}'
                f'</span></div></div>'
            ),
            "data": {},
            "error": str(e),
        }


@router.get("/meta", response_model=list[CardMetaItem])
async def cards_meta():
    """返回所有已注册卡片的元数据列表。

    请求格式:
        GET /cards/meta

    Returns:
        [{name: "dashboard_stats", title: "...", ...}, ...]

    用于前端自动发现和渲染卡片列表
    """
    return [c.to_dict() for c in CARDS]


@router.get("/{name}", response_model=CardRenderResponse)
async def card_data(name: str, request: Request):
    """返回单个卡片渲染结果，信封模式 {html, data, error}。"""
    # 设置当前请求上下文，供卡片 get_data() 读取用户信息
    from src.cards.config_center_card import _current_request  # noqa: PLC0415
    _current_request.set(request)
    try:
        return await _render_card_data(name)
    finally:
        _current_request.set(None)


@router.post("/{name}/action", response_model=CardActionResponse)
async def card_action(name: str, request: Request, payload: dict = None):
    """处理卡片交互动作（统一分发入口）。

    请求格式:
        POST /cards/{name}/action
        Body: {action: "...", ...}

    支持的动作分发（按卡片名称路由）:
        - daemon: 守护进程启停控制
        - telegram: Telegram 配置保存/测试
        - role_picker: 角色代入选股（→ handlers_insights）
        - portfolio: 持仓分析（→ handlers_insights）
        - fetch_control: 手动拉取推文（→ handlers_exec）
        - pipeline_execute: 流水线执行（→ handlers_exec）
        - script_runner: 脚本运行（→ handlers_exec）
        - portrait_generate: 画像生成（→ handlers_data）
        - asset_alias: 资产别名管理（→ handlers_data）
        - api_status: 用户管理（→ handlers_data）

    Returns:
        {ok: True/False, ...} 或 {ok: False, error: "unknown action"}
    """
    # ── 守护进程控制 ──
    if name == "daemon" and payload and payload.get("action") == "toggle":
        try:
            import subprocess
            import sys
            from src.cards import get_card as _get_card  # noqa: PLC0415
            card = _get_card("daemon")
            proc = getattr(card, "_proc", None)

            if proc and proc.poll() is None:
                # 进程正在运行 → 终止
                proc.terminate()
                card._proc = None
            else:
                # 进程未运行 → 启动
                proc = subprocess.Popen([sys.executable, "scripts/daemon_worker.py"])
                card._proc = proc

            _card_cache.pop("daemon", None)  # 清除缓存（状态已变）
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Telegram 配置 ──
    if name == "telegram" and payload:
        try:
            from src.api.dependencies import get_tenant_config  # noqa: PLC0415
            token = payload.get("token", "")
            chat_id = payload.get("chat_id", "")
            cfg = get_tenant_config(request)
            cfg.save_section("telegram", {"bot_token": token, "chat_id": chat_id})
            _card_cache.pop("telegram", None)

            if payload.get("action") == "test":
                import requests as _req  # noqa: PLC0415
                _req.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id,
                                "text": "✅ 投资信号蒸馏台测试消息成功！"})
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 智能问答 ──
    if name == "chat" and payload and payload.get("action") == "ask":
        try:
            from src.interfaces.chat_utils import get_chat_engine, normalize_chat_top_k  # noqa: PLC0415
            question = (payload.get("question") or "").strip()
            if not question:
                return {"ok": False, "error": "问题不能为空"}
            top_k = normalize_chat_top_k(payload.get("top_k", 5))
            answer = get_chat_engine().answer(question, top_k=top_k)
            return {"ok": True, "answer": answer}
        except Exception as e:
            return {"ok": False, "error": f"智能问答暂不可用：{e}"}

    # ── 角色代入选股 ──
    if name == "role_picker" and payload:
        try:
            result = _handle_role_picker(payload)
            return {"ok": True, "html": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 持仓分析 ──
    if name == "portfolio" and payload:
        try:
            result = _handle_portfolio_analysis(payload)
            return {"ok": True, "html": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 手动拉取控制 ──
    if name == "fetch_control" and payload:
        try:
            result = _handle_fetch_control(payload)
            return {'ok': True, 'total': result.get('total_new', 0)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 流水线执行 ──
    if name == "pipeline_execute" and payload:
        return _handle_pipeline_action(payload)

    # ── 脚本运行 ──
    if name == "script_runner" and payload:
        return _handle_script_run(payload)

    # ── 画像生成 ──
    if name == "portrait_generate" and payload:
        return _handle_portrait_generate(payload)

    # ── 资产别名管理 ──
    if name == "asset_alias" and payload:
        return _handle_asset_alias(payload)

    # ── 用户管理 ──
    if name == "api_status" and payload and payload.get("action") in ("add_user", "remove_user"):
        return _handle_user_manage(payload)

    return {"ok": False, "error": "unknown action"}