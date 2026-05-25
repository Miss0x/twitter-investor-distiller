"""阶段 5：Streamlit 本地任务控制台。"""
from __future__ import annotations

import json
import sys
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import requests
import streamlit as st
import yaml
from sqlalchemy import desc

from src.storage.database import db
from src.storage.models import Tweet, User

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT_SECONDS = 10
JOB_STATUS_OPTIONS = ["pending", "running", "paused", "stopping", "stopped", "completed", "failed"]
MODE_OPTIONS = ["recent_3m", "recent_1y", "full_history"]
JOB_TYPE_OPTIONS = ["backfill", "incremental"]
TIMING_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "timing.yaml"


class ApiError(RuntimeError):
    """统一包装 API 错误。"""


def _safe_api_call(fn, *args, **kwargs):
    """统一 API 调用错误边界。"""
    try:
        return fn(*args, **kwargs)
    except ApiError as exc:
        st.error(str(exc))
        return None


def get_api_base_url() -> str:
    if "api_base_url" not in st.session_state:
        st.session_state.api_base_url = DEFAULT_API_BASE_URL
    return str(st.session_state.api_base_url).rstrip("/")


def build_url(path: str) -> str:
    return f"{get_api_base_url()}{path}"


def api_get(path: str) -> Any:
    try:
        response = requests.get(build_url(path), timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiError(f"请求失败：{exc}") from exc

    if response.status_code >= 400:
        detail = extract_error_detail(response)
        raise ApiError(f"GET {path} 失败（{response.status_code}）：{detail}")

    try:
        return response.json()
    except ValueError as exc:
        raise ApiError(f"GET {path} 返回了非 JSON 响应") from exc


def api_post(path: str, payload: dict[str, Any] | None = None) -> Any:
    try:
        response = requests.post(build_url(path), json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiError(f"请求失败：{exc}") from exc

    if response.status_code >= 400:
        detail = extract_error_detail(response)
        raise ApiError(f"POST {path} 失败（{response.status_code}）：{detail}")

    try:
        return response.json()
    except ValueError as exc:
        raise ApiError(f"POST {path} 返回了非 JSON 响应") from exc


def extract_error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or "未知错误"

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if detail:
            return str(detail)
        message = payload.get("message")
        if message:
            return str(message)
    return str(payload)


def fetch_health() -> tuple[bool, str]:
    try:
        payload = api_get("/health")
    except ApiError as exc:
        return False, str(exc)
    status = payload.get("status") if isinstance(payload, dict) else None
    if status == "ok":
        return True, "API 在线"
    return False, f"健康检查异常：{payload}"


def fetch_jobs() -> list[dict[str, Any]]:
    payload = api_get("/jobs")
    return payload if isinstance(payload, list) else []


def fetch_active_job() -> dict[str, Any]:
    payload = api_get("/jobs/active")
    return payload if isinstance(payload, dict) else {"active_job_id": None, "job": None}


def fetch_job_status(job_id: int) -> dict[str, Any]:
    payload = api_get(f"/jobs/{job_id}/status")
    return payload if isinstance(payload, dict) else {}


def fetch_checkpoints(job_id: int) -> list[dict[str, Any]]:
    payload = api_get(f"/jobs/{job_id}/checkpoints")
    return payload if isinstance(payload, list) else []


def fetch_recent_tweets(target_usernames: list[str], limit: int = 20) -> list[dict[str, Any]]:
    session = db.get_session()
    try:
        query = (
            session.query(Tweet, User)
            .join(User, Tweet.user_id == User.id)
            .order_by(desc(Tweet.created_at_twitter))
        )
        if target_usernames:
            query = query.filter(User.username.in_(target_usernames))

        rows = query.limit(limit).all()
        tweets: list[dict[str, Any]] = []
        for tweet, user in rows:
            tweets.append(
                {
                    "username": user.username,
                    "created_at_twitter": tweet.created_at_twitter.isoformat() if tweet.created_at_twitter else "",
                    "tweet_id": tweet.tweet_id,
                    "text": tweet.text,
                    "url": tweet.url or "",
                    "has_media": bool(tweet.has_media),
                }
            )
        return tweets
    finally:
        with suppress(Exception):
            session.close()


def parse_usernames(raw_text: str) -> list[str]:
    normalized = raw_text.replace("\n", ",")
    usernames: list[str] = []
    for item in normalized.split(","):
        cleaned = item.strip().lstrip("@")
        if cleaned:
            usernames.append(cleaned)
    seen: set[str] = set()
    unique_usernames: list[str] = []
    for username in usernames:
        if username not in seen:
            seen.add(username)
            unique_usernames.append(username)
    return unique_usernames


def format_job_label(job: dict[str, Any]) -> str:
    usernames = ", ".join(job.get("target_usernames") or [])
    return f"#{job.get('id')} | {job.get('status')} | {job.get('mode')} | {usernames}"


def status_allows_action(status: str, action: str) -> bool:
    allowed_actions = {
        "pending": {"start"},
        "running": {"pause", "stop"},
        "paused": {"resume", "stop"},
        "stopping": set(),
        "stopped": {"restart"},
        "completed": {"restart"},
        "failed": {"restart"},
    }
    return action in allowed_actions.get(status, set())


# ── 抓取等待时间配置 ──────────────────────────────

def load_timing_config() -> dict:
    if not TIMING_CONFIG_PATH.exists():
        return {"max_scroll_rounds": 200, "no_new_items_limit": 10,
                "page_ready_timeout_seconds": 180, "settle_after_scroll_ms": 3000}
    with open(TIMING_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return (data or {}).get("active", {})


def save_timing_config(cfg: dict) -> None:
    TIMING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "profiles": {
            "fast": {"page_ready_timeout_seconds": 60, "settle_after_scroll_ms": 1200,
                     "max_scroll_rounds": 80, "no_new_items_limit": 5},
            "slow": {"page_ready_timeout_seconds": 180, "settle_after_scroll_ms": 3000,
                     "max_scroll_rounds": 120, "no_new_items_limit": 8},
            "patient": {"page_ready_timeout_seconds": 300, "settle_after_scroll_ms": 5000,
                        "max_scroll_rounds": 200, "no_new_items_limit": 12},
        },
        "active": cfg,
    }
    with open(TIMING_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(wrapper, f, allow_unicode=True, default_flow_style=False)


def render_timing_sidebar() -> None:
    st.header("⏱ 抓取等待时间")
    cfg = load_timing_config()

    profile = st.radio(
        "预设模式",
        ["自定义", "快节点", "慢节点", "极度耐心"],
        index=0,
        horizontal=True,
        help="一键切换预设。选「自定义」则使用下方滑块。",
    )
    profile_map = {
        "快节点": {"page_ready_timeout_seconds": 60, "settle_after_scroll_ms": 1200,
                   "max_scroll_rounds": 80, "no_new_items_limit": 5},
        "慢节点": {"page_ready_timeout_seconds": 180, "settle_after_scroll_ms": 3000,
                   "max_scroll_rounds": 120, "no_new_items_limit": 8},
        "极度耐心": {"page_ready_timeout_seconds": 300, "settle_after_scroll_ms": 5000,
                     "max_scroll_rounds": 200, "no_new_items_limit": 12},
    }
    if profile != "自定义":
        cfg = profile_map[profile]

    st.caption("页面就绪等待（秒）")
    page_timeout = st.slider("page_ready_timeout_seconds", 30, 600, cfg.get("page_ready_timeout_seconds", 180),
                             step=15, label_visibility="collapsed")
    st.caption("滚动后稳定等待（毫秒）")
    settle_ms = st.slider("settle_after_scroll_ms", 500, 10000, cfg.get("settle_after_scroll_ms", 3000),
                          step=250, label_visibility="collapsed")
    st.caption("最大滚动轮数")
    max_rounds = st.slider("max_scroll_rounds", 20, 400, cfg.get("max_scroll_rounds", 200),
                           step=10, label_visibility="collapsed")
    st.caption("连续无新内容容忍轮数")
    no_new_limit = st.slider("no_new_items_limit", 3, 30, cfg.get("no_new_items_limit", 10),
                             step=1, label_visibility="collapsed")

    new_cfg = {
        "page_ready_timeout_seconds": page_timeout,
        "settle_after_scroll_ms": settle_ms,
        "max_scroll_rounds": max_rounds,
        "no_new_items_limit": no_new_limit,
    }

    if new_cfg != cfg or profile != "自定义":
        save_timing_config(new_cfg)
        st.success("等待时间已更新，下次任务生效")

    st.divider()


def create_job_section() -> None:
    """创建任务的表单区域。"""
    st.subheader("创建任务")
    with st.form("create_job_form"):
        raw_usernames = st.text_area(
            "目标用户名",
            value="TJ_Research\ndearbaibabybus",
            help="支持逗号或换行分隔，@ 可省略",
            height=110,
        )
        col1, col2 = st.columns(2)
        with col1:
            mode = st.selectbox("抓取模式", MODE_OPTIONS, index=0)
        with col2:
            job_type = st.selectbox("任务类型", JOB_TYPE_OPTIONS, index=0)
        submitted = st.form_submit_button("创建任务", use_container_width=True)

    if submitted:
        usernames = parse_usernames(raw_usernames)
        if not usernames:
            st.error("请至少输入一个用户名")
            return
        try:
            result = api_post(
                "/jobs",
                {
                    "usernames": usernames,
                    "mode": mode,
                    "job_type": job_type,
                },
            )
        except ApiError as exc:
            st.error(str(exc))
            return

        job = result.get("job", {}) if isinstance(result, dict) else {}
        message = result.get("message", "任务创建成功") if isinstance(result, dict) else "任务创建成功"
        st.success(f"{message}：任务 #{job.get('id')}")
        st.session_state.selected_job_id = job.get("id")
        st.rerun()


def ensure_selected_job_id(jobs: list[dict[str, Any]], active_job_payload: dict[str, Any]) -> int | None:
    selected_job_id = st.session_state.get("selected_job_id")
    available_ids = [job.get("id") for job in jobs if job.get("id") is not None]
    active_job = active_job_payload.get("job") if isinstance(active_job_payload, dict) else None

    if selected_job_id in available_ids:
        return selected_job_id
    if active_job and active_job.get("id") in available_ids:
        st.session_state.selected_job_id = active_job.get("id")
        return active_job.get("id")
    if available_ids:
        st.session_state.selected_job_id = available_ids[0]
        return available_ids[0]
    st.session_state.selected_job_id = None
    return None


def render_job_table(jobs: list[dict[str, Any]], selected_job_id: int | None) -> int | None:
    st.subheader("任务列表")
    if not jobs:
        st.info("当前还没有任务")
        return None

    options = {format_job_label(job): job.get("id") for job in jobs}
    labels = list(options.keys())
    default_index = 0
    if selected_job_id is not None:
        for index, label in enumerate(labels):
            if options[label] == selected_job_id:
                default_index = index
                break

    selected_label = st.selectbox("选择任务", labels, index=default_index)
    selected_job_id = options[selected_label]
    st.session_state.selected_job_id = selected_job_id

    table_rows = []
    for job in jobs:
        table_rows.append(
            {
                "id": job.get("id"),
                "status": job.get("status"),
                "mode": job.get("mode"),
                "job_type": job.get("job_type"),
                "current_username": job.get("current_username") or "",
                "progress_percent": job.get("progress_percent"),
                "tweets_collected_total": job.get("tweets_collected_total"),
                "users_progress": f"{job.get('users_completed', 0)}/{job.get('users_total', 0)}",
                "target_usernames": ", ".join(job.get("target_usernames") or []),
                "updated_at": job.get("updated_at") or "",
            }
        )
    st.dataframe(table_rows, use_container_width=True, hide_index=True)
    return selected_job_id


def render_selected_job(job: dict[str, Any], job_status_payload: dict[str, Any], checkpoints: list[dict[str, Any]]) -> None:
    st.subheader(f"任务详情 #{job.get('id')}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("状态", job.get("status") or "-")
    col2.metric("当前用户", job.get("current_username") or "-")
    col3.metric("进度", f"{job.get('progress_percent', 0):.1f}%")
    col4.metric("已采集推文", job.get("tweets_collected_total") or 0)

    col5, col6, col7 = st.columns(3)
    col5.metric("已完成用户", job.get("users_completed") or 0)
    col6.metric("总用户数", job.get("users_total") or 0)
    col7.metric("进程内运行", "是" if job_status_payload.get("is_running_in_process") else "否")

    st.progress(min(max(float(job.get("progress_percent") or 0) / 100, 0.0), 1.0))

    with st.expander("任务原始信息", expanded=False):
        st.json(job)

    render_control_buttons(job)
    render_checkpoint_section(checkpoints)
    render_log_summary(job, job_status_payload, checkpoints)


def render_control_buttons(job: dict[str, Any]) -> None:
    st.subheader("任务控制")
    status = str(job.get("status") or "")
    job_id = job.get("id")

    col1, col2, col3, col4, col5 = st.columns(5)
    action_map = [
        (col1, "启动", "start"),
        (col2, "恢复", "resume"),
        (col3, "暂停", "pause"),
        (col4, "停止", "stop"),
        (col5, "重新开始", "restart"),
    ]

    for column, label, action in action_map:
        disabled = not status_allows_action(status, action)
        if column.button(label, key=f"{action}_{job_id}", use_container_width=True, disabled=disabled):
            try:
                result = api_post(f"/jobs/{job_id}/{action}")
            except ApiError as exc:
                st.error(str(exc))
                return
            message = result.get("message", f"任务已{label}") if isinstance(result, dict) else f"任务已{label}"
            st.success(message)
            st.rerun()

    if status not in JOB_STATUS_OPTIONS:
        st.warning(f"发现未识别状态：{status}")


def render_checkpoint_section(checkpoints: list[dict[str, Any]]) -> None:
    st.subheader("Checkpoint")
    if not checkpoints:
        st.info("该任务还没有 checkpoint")
        return

    rows = []
    for checkpoint in checkpoints:
        rows.append(
            {
                "username": checkpoint.get("username"),
                "last_seen_tweet_id": checkpoint.get("last_seen_tweet_id") or "",
                "last_seen_tweet_time": checkpoint.get("last_seen_tweet_time") or "",
                "scroll_iterations": checkpoint.get("scroll_iterations") or 0,
                "consecutive_no_new_items": checkpoint.get("consecutive_no_new_items") or 0,
                "tweets_collected": checkpoint.get("tweets_collected") or 0,
                "updated_at": checkpoint.get("updated_at") or "",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_log_summary(job: dict[str, Any], job_status_payload: dict[str, Any], checkpoints: list[dict[str, Any]]) -> None:
    st.subheader("简化日志 / 状态摘要")
    last_error = job.get("last_error")
    if last_error:
        st.error(last_error)
    else:
        st.success("当前没有 last_error")

    summary = {
        "active_job_id": job_status_payload.get("active_job_id"),
        "is_running_in_process": job_status_payload.get("is_running_in_process"),
        "job_status": job.get("status"),
        "current_username": job.get("current_username"),
        "users_progress": f"{job.get('users_completed', 0)}/{job.get('users_total', 0)}",
        "tweets_collected_total": job.get("tweets_collected_total") or 0,
        "checkpoint_count": len(checkpoints),
        "latest_checkpoint_username": checkpoints[0].get("username") if checkpoints else None,
        "latest_checkpoint_updated_at": checkpoints[0].get("updated_at") if checkpoints else None,
    }
    st.json(summary)


def render_recent_tweets_section(job: dict[str, Any]) -> None:
    st.subheader("最近已录入内容")
    target_usernames = job.get("target_usernames") or []

    try:
        tweets = fetch_recent_tweets(target_usernames=target_usernames, limit=20)
    except Exception as exc:
        st.error(f"读取已录入内容失败：{exc}")
        return

    if target_usernames:
        st.caption(f"当前仅展示所选任务相关账号的最近内容：{', '.join(target_usernames)}")

    if not tweets:
        st.info("当前没有查到已录入内容")
        return

    rows = []
    for item in tweets:
        rows.append(
            {
                "username": item["username"],
                "created_at_twitter": item["created_at_twitter"],
                "tweet_id": item["tweet_id"],
                "has_media": "是" if item["has_media"] else "否",
                "text": item["text"],
                "url": item["url"],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Twitter 蒸馏控制台", page_icon="🧠", layout="wide")

    # ── 全局样式注入 ──
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; }
    .stButton > button {
        border-radius: 6px; font-weight: 500; font-size: 0.875rem;
        transition: all 0.15s ease; border: 1px solid rgba(255,255,255,0.08);
    }
    .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
    [data-testid="stMetricValue"] { font-size: 1.75rem; font-weight: 700; }
    .stRadio > div { gap: 0.5rem; }
    .stRadio label { padding: 0.25rem 0.75rem; border-radius: 6px; }
    .st-expander { border-radius: 8px; border: 1px solid rgba(255,255,255,0.06); }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #0d1117 0%, #161b22 100%); }
    section[data-testid="stSidebar"] > div { padding-top: 1rem; }
    </style>
    """, unsafe_allow_html=True)

    # ── 侧边栏 ──
    with st.sidebar:
        st.markdown("### 🔗 连接")
        api_base_url = st.text_input("API 地址", value=get_api_base_url(), label_visibility="collapsed")
        st.session_state.api_base_url = api_base_url.rstrip("/")
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()
        st.divider()
        render_timing_sidebar()

    # ── 健康检查 ──
    health_ok, health_message = fetch_health()
    jobs: list[dict[str, Any]] = []
    active_job_payload: dict[str, Any] = {"active_job_id": None, "job": None}
    if health_ok:
        try:
            jobs = fetch_jobs()
            active_job_payload = fetch_active_job()
        except ApiError as exc:
            health_ok = False
            health_message = str(exc)

    # ── 顶部状态栏 ──
    c1, c2, c3, c4 = st.columns([1, 1, 1, 5])
    with c1:
        if health_ok:
            st.markdown("🟢 **API 正常**")
        else:
            st.error(f"🔴 {health_message}")
    with c2:
        st.markdown(f"📦 **{len(jobs)} 任务**")
    with c3:
        active_id = active_job_payload.get("active_job_id") if isinstance(active_job_payload, dict) else None
        st.markdown("⚡ **运行中**" if active_id else "💤 空闲")
    with c4:
        st.caption("Twitter 用户蒸馏 · 抓取 → 分析 → 画像")

    # ── 实时监控 ──
    _render_daemon_control()

    # ── Telegram 通知 ──
    _render_telegram_config()

    st.divider()

    # ── 主区域 ──
    tab1, tab2, tab3 = st.tabs(["📊 抓取仪表盘", "⚙️ 分析流水线", "📡 信号与洞察"])
    with tab1:
        _render_dashboard(health_ok, jobs, active_job_payload)
    with tab2:
        render_pipeline_section()
    with tab3:
        _render_insights_tab()


def _render_dashboard(health_ok: bool, jobs: list[dict[str, Any]], active_job_payload: dict[str, Any]) -> None:
    """仪表盘：概览 + 任务管理"""
    if not health_ok:
        st.warning("API 不可用，请检查服务是否启动")
        return

    # ── 准确率面板 ──
    _render_accuracy_panel()

    # ── 统计卡片 ──
    from collections import Counter
    status_counts = Counter(j.get("status") for j in jobs)
    c1, c2, c3, c4, c5 = st.columns(5)
    status_config = [
        ("pending", "⏳", "#ffc107"), ("running", "⚡", "#0d6efd"),
        ("completed", "✅", "#198754"), ("failed", "❌", "#dc3545"),
        ("paused", "⏸️", "#6c757d"),
    ]
    for col, (stt, emoji, color) in zip([c1,c2,c3,c4,c5], status_config):
        with col:
            n = status_counts.get(stt, 0)
            st.markdown(f"<div style='text-align:center;padding:8px;border-radius:8px;"
                        f"border-left:3px solid {color};background:#1a1a2e'>"
                        f"<span style='font-size:12px;color:#888'>{emoji} {stt}</span><br>"
                        f"<span style='font-size:24px;font-weight:bold'>{n}</span></div>",
                        unsafe_allow_html=True)

    st.divider()

    # ── 任务列表 + 新建 ──
    left_col, right_col = st.columns([1, 2])
    with left_col:
        create_job_section()

    with right_col:
        selected_job_id = ensure_selected_job_id(jobs, active_job_payload)
        selected_job_id = render_job_table(jobs, selected_job_id)
        if selected_job_id is None:
            return

        selected_job = next((job for job in jobs if job.get("id") == selected_job_id), None)
        if selected_job is None:
            st.warning("未找到所选任务")
            return

        try:
            job_status_payload = fetch_job_status(selected_job_id)
            checkpoints = fetch_checkpoints(selected_job_id)
        except ApiError as exc:
            st.error(str(exc))
            return

        job_payload = job_status_payload.get("job") if isinstance(job_status_payload, dict) else None
        current_job = job_payload or selected_job
        render_selected_job(current_job, job_status_payload, checkpoints)
        render_recent_tweets_section(current_job)


# ── 流水线任务队列 ──

def render_pipeline_section() -> None:
    try:
        all_data = api_get("/pipeline/tasks")
    except ApiError as exc:
        st.warning(f"API 不可用: {exc}")
        return

    # 自动刷新
    auto = st.checkbox("🔄 每 5 秒自动刷新", key="auto_refresh")
    if auto:
        time.sleep(5)
        st.rerun()

    # ── 执行进度 ──
    try:
        all_data = api_get("/pipeline/tasks")
    except ApiError as exc:
        st.warning(f"API 不可用: {exc}")
        return

    running = all_data.get("running", False)
    progress = all_data.get("progress", {})

    if running:
        st.info(f"⏳ 执行中: {progress.get('msg','')} ({progress.get('done',0)}/{progress.get('total',0)})")

    # ── 类型选择 ──
    task_type = st.radio(
        "选择操作类型",
        ["analyze", "fetch_price", "fetch_crypto", "portrait"],
        format_func=lambda x: {"analyze": "📝 分析推文", "fetch_price": "📈 拉取股价", "fetch_crypto": "₿ 加密货币", "portrait": "🖼 生成画像"}[x],
        horizontal=True,
        key="active_task_type",
    )

    # ── 加载当前类型的任务数据 ──
    try:
        data = api_get(f"/pipeline/tasks?task_type={task_type}")
    except ApiError:
        st.warning("API 不可用")
        return

    tasks = data.get("tasks", [])
    pending = [t for t in tasks if t["status"] == "pending"]
    done = [t for t in tasks if t["status"] == "done"]
    failed = [t for t in tasks if t["status"] == "failed"]

    st.caption(f"待办 {len(pending)} | 完成 {len(done)} | 失败 {len(failed)}")

    if not pending:
        st.info("暂无待办任务")
    else:
        # ── 勾选列表 ──
        all_ids = [t["id"] for t in pending]
        selected = []
        
        # 操作栏：一行
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            if st.button("全选", key="all_btn", use_container_width=True):
                for tid in all_ids: st.session_state[f"cb_{tid}"] = True
                st.rerun()
        with c2:
            if st.button("前5", key="top5_btn", use_container_width=True):
                for tid in all_ids[:5]: st.session_state[f"cb_{tid}"] = True
                st.rerun()
        with c3:
            if st.button("取消", key="clear_btn", use_container_width=True):
                for tid in all_ids: st.session_state[f"cb_{tid}"] = False
                st.rerun()
        with c4:
            if task_type == "analyze" and st.button("🔎 过滤", key="filter_btn", use_container_width=True):
                try:
                    api_post("/pipeline/filter")
                    st.success("过滤已启动"); time.sleep(3)
                    api_post("/pipeline/tasks/seed"); st.rerun()
                except ApiError as e: st.error(str(e))

        # 勾选框（selected 在这填充）
        with st.container(height=max(200, min(400, 35 * len(pending)))):
            for t in pending:
                payload = t.get("payload", {})
                if task_type == "analyze":
                    label = f"#{payload.get('tweet_id','?')} | {payload.get('text','')[:50]}"
                    extra = f"@{payload.get('username','?')}"
                elif task_type == "fetch_price":
                    label = extra = payload.get("ticker", "?")
                elif task_type == "fetch_crypto":
                    label = extra = f"₿ {payload.get('ticker', '?')}"
                else:
                    username = payload.get("username", "?")
                    wlabel = payload.get("label", "")
                    live_count = payload.get("tweet_count", 0)
                    label = f"🖼 {username}"
                    extra = f"{live_count} 条 · {wlabel}"
                cb = st.checkbox(str(label), key=f"cb_{t['id']}", help=extra)
                if cb:
                    selected.append(t["id"])

        # 执行按钮（放在勾选后面，selected 此时已填充）
        if st.button(f"▶ 执行选中 ({len(selected)})", key="exec_btn", disabled=not selected, use_container_width=True):
            try:
                resp = api_post("/pipeline/tasks/execute", {"task_ids": selected})
                st.success(resp.get("message", "OK")); time.sleep(1); st.rerun()
            except ApiError as e: st.error(str(e))

    # 失败列表
    if failed:
        with st.expander(f"⚠️ 失败/需人工 ({len(failed)})", expanded=len(failed) < 10):
            for t in failed[:50]:
                p = t.get("payload", {})
                sources = p.get("sources", [])
                src_md = ""
                if sources:
                    s0 = sources[0]
                    url = s0.get("url", "")
                    line = f"@{s0.get('user','?')}: {s0.get('text','')[:60]} ({s0.get('date','')})"
                    src_md = f"[{line}]({url})" if url else line
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                with c1:
                    st.caption(f"#{t['id']} **{p.get('ticker','?')}**: {t.get('error_msg','?')[:60]}")
                    if src_md: st.caption(f"📌 {src_md}")
                with c2:
                    if st.button("🔄 重试", key=f"retry_{t['id']}"):
                        api_post(f"/pipeline/tasks/{t['id']}/retry"); st.rerun()
                with c3:
                    nt = st.text_input("修", key=f"edit_{t['id']}", label_visibility="collapsed", placeholder="ticker")
                    if nt and st.button("💾", key=f"save_{t['id']}"):
                        api_post(f"/pipeline/tasks/{t['id']}/edit", {"ticker": nt}); st.rerun()
                with c4:
                    if st.button("🚫 跳过", key=f"skip_{t['id']}"):
                        api_post(f"/pipeline/tasks/{t['id']}/skip"); st.rerun()

    # 已完成
    if task_type in ("fetch_price", "fetch_crypto"):
        ep = "/pipeline/tasks/fetched" if task_type == "fetch_price" else "/pipeline/tasks/crypto_fetched"
        try:
            fr = api_get(ep)
            ft = fr.get("tickers", [])
            if ft:
                with st.expander(f"✅ 已完成 ({len(ft)} 只)", expanded=False):
                    st.caption(", ".join(ft[:100]))
        except ApiError: pass


def _render_accuracy_panel() -> None:
    """📊 准确率回溯面板 — Phase 1 #2 模块"""
    from pathlib import Path as _Path
    import json as _json

    st.subheader("📊 分析师准确率")

    acc_files = list(_Path("data/accuracy").glob("*_accuracy.json"))
    if not acc_files:
        st.caption("暂无准确率数据，运行 python scripts/backtest_accuracy.py 生成")
        return

    # 读取
    all_data = []
    for fp in acc_files:
        d = _json.loads(fp.read_text(encoding="utf-8"))
        all_data.append(d)

    # 总览表
    overview_rows = []
    for d in all_data:
        r30 = d["returns_30d"]
        overview_rows.append({
            "分析师": d["username"],
            "信号数": d["total_signals"],
            "30日胜率": f"{r30['win_rate']*100:.0f}%",
            "30日均收益": f"{r30['avg_return']*100:+.1f}%",
            "夏普比率": r30["sharpe"],
            "最大盈利": f"{r30['max_return']*100:+.0f}%",
            "最大亏损": f"{r30['min_return']*100:+.0f}%",
        })
    st.dataframe(overview_rows, use_container_width=True, hide_index=True)

    # 每位分析师展开详情
    for d in all_data:
        with st.expander(f"{d['username']} — 板块 & 股票详情"):
            # 按板块
            if d.get("by_topic"):
                st.markdown("**按板块（Topic）**")
                topic_rows = []
                for topic, stats in sorted(d["by_topic"].items(), key=lambda x: x[1].get("avg_return") or -99, reverse=True):
                    if stats["count"]:
                        topic_rows.append({
                            "板块": topic,
                            "信号数": stats["count"],
                            "胜率": f"{stats['win_rate']*100:.0f}%",
                            "均收益": f"{stats['avg_return']*100:+.1f}%",
                            "夏普": stats.get("sharpe", 0),
                        })
                if topic_rows:
                    st.dataframe(topic_rows, use_container_width=True, hide_index=True)

            # 按股票
            st.markdown("**按股票 TOP 10**")
            stock_rows = []
            for ticker, stats in sorted(d["by_stock"].items(), key=lambda x: x[1]["returns_30d"].get("avg_return") or -99, reverse=True)[:10]:
                r30s = stats["returns_30d"]
                if r30s["count"]:
                    stock_rows.append({
                        "股票": ticker,
                        "信号": r30s["count"],
                        "胜率": f"{r30s['win_rate']*100:.0f}%",
                        "均收益": f"{r30s['avg_return']*100:+.1f}%",
                    })
            if stock_rows:
                st.dataframe(stock_rows, use_container_width=True, hide_index=True)


def _render_insights_tab() -> None:
    """📡 信号与洞察面板 — Phase 3-4-5 产出。"""
    from pathlib import Path as _Path
    import json as _json

    # ── 角色代入选股 ──
    st.subheader("🤖 角色代入选股")
    col1, col2 = st.columns([1, 2])
    with col1:
        analyst = st.selectbox("分析师", ["TJ_Research", "dearbaibabybus"])
    with col2:
        sectors = _get_sector_options()
        sector = st.selectbox("行业板块（SIC 标准分类）", list(sectors.keys()),
                              help="Polygon SIC 官方行业分类，无标签污染")

    # 显示该行业的股票池
    stocks_in_sector = sectors.get(sector, [])
    st.caption(f"该行业共 {len(stocks_in_sector)} 只股票（分析师历史覆盖）")

    col3, col4 = st.columns([3, 1])
    with col3:
        custom_stocks = st.text_input("手动加减股票（逗号分隔）", placeholder="如: LRCX,AMAT 或不想要某只写 -INTC")
    with col4:
        refresh = st.checkbox("🔄 实时价格", value=True, help="每次生成时拉取最新股价，不勾选用缓存")

    go = st.button("🚀 生成选股方案", type="primary")

    if go:
        final_stocks = _build_stock_pool(stocks_in_sector, custom_stocks)
        if not final_stocks:
            st.warning("股票池为空，请选择行业或手动添加")
        else:
            with st.spinner(f"正在模拟 {analyst} 在 {sector} 的决策（{len(final_stocks)} 只股票）..."):
                result = _run_role_picker_v2(analyst, sector, final_stocks, refresh)
                if result:
                    st.markdown(result)
                else:
                    st.error("生成失败，检查 API 配置")

    st.divider()

    # ── 持仓建议 ──
    st.subheader("💼 我的持仓顾问")
    upload_method = st.radio("输入方式", ["📁 CSV 文件", "✏️ 文字输入", "📸 截图上传"], horizontal=True)

    if upload_method == "📁 CSV 文件":
        csv_file = st.file_uploader("上传持仓 CSV", type=["csv"])
        if csv_file:
            st.dataframe(_parse_csv(csv_file))
            if st.button("🔍 分析持仓", key="csv_analyze"):
                _run_portfolio_analyzer(csv_file.getvalue().decode(), None, None)
    elif upload_method == "✏️ 文字输入":
        text_input = st.text_area("输入持仓信息", height=150, placeholder="NVDA 100股 成本$110\nAVGO 50股 成本$320\n...")
        if st.button("🔍 分析持仓", key="text_analyze") and text_input:
            _run_portfolio_analyzer(text_input, None, None)
    else:
        img_file = st.file_uploader("上传持仓截图", type=["png", "jpg", "jpeg"])
        if img_file:
            st.image(img_file, width=300)
            if st.button("🔍 分析截图", key="img_analyze"):
                _run_portfolio_analyzer(None, img_file, None)

    st.divider()

    # ── 最新共识 ──
    st.subheader("📡 最新共识")
    cons_dir = _Path("data/consensus")
    if cons_dir.exists():
        latest = []
        for fp in cons_dir.glob("*_consensus.json"):
            data = _json.loads(fp.read_text(encoding="utf-8"))
            if data:
                entry = data[-1]
                entry["ticker"] = fp.stem.replace("_consensus", "")
                latest.append(entry)
        latest.sort(key=lambda x: x.get("consensus_score", 0), reverse=True)
        rows = []
        for e in latest[:10]:
            multi = "🔥" if len(e.get("analysts_in_window", [])) >= 2 else ""
            rows.append({
                "股票": e["ticker"],
                "共识分": e["consensus_score"],
                "信号数": e.get("signal_count", 0),
                "分析师": ", ".join(e.get("analysts_in_window", [])),
                "联动": multi,
            })
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.caption("运行 python scripts/compute_consensus.py 生成")

    # ── 板块轮动 ──
    st.subheader("🔥 板块轮动")
    rot_dir = _Path("data/rotation")
    if rot_dir.exists():
        for fp in sorted(rot_dir.glob("*_rotation.json")):
            username = fp.stem.replace("_rotation", "")
            data = _json.loads(fp.read_text(encoding="utf-8"))
            # 最新 4 周
            weeks = sorted({r["week"] for r in data})
            if weeks:
                latest_week = weeks[-1]
                hot = sorted([r for r in data if r["week"] == latest_week], key=lambda x: x["z_score"], reverse=True)[:5]
                with st.expander(f"{username} — {latest_week}"):
                    for r in hot:
                        st.metric(r["topic"], f"{r['z_score']:+.1f}σ", f"提及 {r['count']} 次")
    else:
        st.caption("运行 python scripts/compute_rotation.py 生成")

    # ── 异常检测 ──
    st.subheader("⚠️ 最近异常")
    anom_dir = _Path("data/anomaly")
    if anom_dir.exists():
        for fp in sorted(anom_dir.glob("*_anomaly.json")):
            tag = fp.stem.replace("_anomaly", "")
            data = _json.loads(fp.read_text(encoding="utf-8"))
            anomalies = [r for r in data if r["anomaly"]][-3:]
            if anomalies:
                with st.expander(f"{tag}: {len(anomalies)} 条异常（最近）"):
                    for a in anomalies:
                        st.text(f"{a['window_start']}~{a['window_end']} KL={a['kl_avg']:.2f}")
                        st.caption(f"topics: {', '.join(a['topics'][:3])}")
    else:
        st.caption("运行 python scripts/detect_anomaly.py 生成")

    # ── 关联网络 ──
    st.subheader("🕸️ 信源推荐")
    net_path = _Path("data/network/investor_network.json")
    if net_path.exists():
        net = _json.loads(net_path.read_text(encoding="utf-8"))
        recs = net.get("recommendations", [])[:5]
        if recs:
            for r in recs:
                st.metric(r["user"], f"{r['in_degree']} 次被引用")
    else:
        st.caption("运行 python scripts/build_network.py 生成")


def _run_role_picker(analyst: str, sector: str) -> str | None:
    """调用 #7 角色代入：加载画像+基本面+K线，调 LLM 生成选股方案。"""
    import json as _json
    from pathlib import Path as _Path
    from src.ai.llm_client import chat

    # 加载画像
    candidates = sorted(_Path("data/pipeline").glob(f"{analyst}*portrait.md"))
    if not candidates:
        short = analyst.split("_")[0]
        candidates = sorted(_Path("data/pipeline").glob(f"{short}*portrait.md"))
    portrait = candidates[-1].read_text(encoding="utf-8")[:3000] if candidates else "无画像"

    # 加载该分析师提到的股票 + 基本面 + K线
    fundamentals = {}
    if _Path("data/fundamental_cache.json").exists():
        fundamentals = _json.loads(_Path("data/fundamental_cache.json").read_text(encoding="utf-8"))
    prices = {}
    if _Path("data/prices.json").exists():
        prices = _json.loads(_Path("data/prices.json").read_text(encoding="utf-8"))

    # 收集板块内股票
    search_terms = [t.strip().lower() for t in sector.replace("/", " ").split() if t.strip()]
    tickers = set()
    for fp in _Path("data/pipeline").glob(f"{analyst}*analyzed_cleaned.json"):
        for r in _json.loads(fp.read_text(encoding="utf-8")):
            sectors_str = " ".join(r.get("mentioned_sectors", [])).lower()
            text = (r.get("text", "") or "").lower()
            topic = (r.get("topic", "") or "").lower()
            haystack = f"{sectors_str} {topic} {text}"
            if any(term in haystack for term in search_terms):
                for s in r.get("stock_details", []):
                    t = s.get("ticker", "").upper()
                    if t: tickers.add(t)

    # 构建股票池表
    stock_rows = []
    for t in sorted(tickers)[:15]:
        f = fundamentals.get(t, {})
        bars = prices.get(t, {}).get("results", [])
        lc = f"${bars[-1]['c']:.0f}" if bars else "?"
        pe = f"{f.get('pe_ratio','?'):.0f}" if f.get('pe_ratio') else "?"
        roe = f"{f.get('roe','?'):.0f}%" if f.get('roe') else "?"
        chg = ""
        if bars and len(bars) >= 22:
            chg = f"{(bars[-1]['c']-bars[-22]['c'])/bars[-22]['c']*100:+.1f}%"
        stock_rows.append(f"| {t} | {pe} | {roe} | {lc} | {chg} |")

    stock_table = "| Ticker | PE | ROE | 价格 | 30日 |\n|--------|-----|-----|------|------|\n" + "\n".join(stock_rows)

    prompt = f"""[Role]
你是 {analyst} 的投资决策模拟器。以下是他的完整投资风格画像：

{portrait}

[Task]
基于以上画像的投资框架，从以下 {sector} 板块股票池中选择 3-5 只最符合其理念的标的。
说明理由（引用画像具体维度），分配仓位（总和 100%），给入场区间和止损。

[Stock Pool]
{stock_table}

[Output]
用中文 Markdown 格式，含选股表格和每只的 reasoning。"""

    try:
        return chat(messages=[{"role": "user", "content": prompt}], role="analyzer", max_tokens=4096, temperature=0.5)
    except Exception as e:
        return None


def _parse_csv(uploaded_file):
    """解析上传的 CSV 文件。"""
    import pandas as _pd
    import io as _io
    return _pd.read_csv(_io.BytesIO(uploaded_file.getvalue() if hasattr(uploaded_file, 'getvalue') else uploaded_file))


def _run_portfolio_analyzer(text: str | None, image_file, csv_bytes: bytes | None) -> None:
    """调用 LLM 分析持仓。支持文字、CSV、截图三种输入。"""
    import json as _json
    from pathlib import Path as _Path
    from src.ai.llm_client import chat
    import streamlit as _st

    fundamentals = {}
    if _Path("data/fundamental_cache.json").exists():
        fundamentals = _json.loads(_Path("data/fundamental_cache.json").read_text(encoding="utf-8"))

    portraits = []
    for fp in sorted(_Path("data/pipeline").glob("*全量*portrait.md")):
        username = fp.stem.replace("_全量_portrait", "")
        portraits.append(f"## {username}\n{fp.read_text(encoding='utf-8')[:1500]}")

    acc_text = ""
    for fp in _Path("data/accuracy").glob("*.json"):
        u = fp.stem.replace("_accuracy", "")
        d = _json.loads(fp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate", "?")
        acc_text += f"- {u}: 30日胜率 {wr*100:.0f}%\n" if isinstance(wr, (int, float)) else ""

    portrait_text = "\n".join(portraits)
    prompt = f"""你是投资顾问。基于以下分析师画像和准确率，分析我的持仓。

[分析师画像]
{portrait_text}

[准确率]
{acc_text}

[我的持仓]
{text or "见截图"}

每只持仓股给出: 1) 分析师怎么看（引用画像）2) 建议（仓位/成本/止损）3) 风险提示。中文Markdown。"""

    with _st.spinner("正在分析..."):
        try:
            messages = [{"role": "user", "content": prompt}]
            if image_file is not None:
                import base64 as _b64
                img_bytes = image_file.getvalue()
                img_b64 = _b64.b64encode(img_bytes).decode()
                messages[0]["content"] = [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    {"type": "text", "text": prompt},
                ]
            result = chat(messages=messages, role="analyzer", max_tokens=4096, temperature=0.5)
            _st.markdown(result)
        except Exception as e:
            _st.error(f"分析失败: {e}")


# ══════ 实时监控 Daemon ══════

def _render_daemon_control() -> None:
    """实时触发开关 + 状态监控 — Step 3 #3 模块。"""
    from pathlib import Path as _Path
    import json as _json
    import subprocess as _sp
    import time as _time

    if "daemon_script" not in st.session_state:
        st.session_state.daemon_script = None
        st.session_state.daemon_proc = None
        st.session_state.daemon_log = []
        st.session_state.daemon_started_at = None

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    # 如果进程还在跑，更新状态
    if st.session_state.daemon_proc is not None:
        poll = st.session_state.daemon_proc.poll()
        if poll is not None:
            st.session_state.daemon_proc = None
            st.session_state.daemon_log.append(f"{_time.strftime('%H:%M:%S')} Daemon 已停止 (exit={poll})")

    with col1:
        if st.session_state.daemon_proc is None:
            if st.button("▶️ 启动实时监控", type="primary"):
                # daemon 内联脚本
                inline = textwrap.dedent(f"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, r'{_Path.cwd()}')
from src.storage.database import db
from src.storage.models import Tweet, PipelineTask

db.init_db()
session = db.get_session()
last_id = 0
state = Path('data/auto_scheduler_state.json')
if state.exists():
    last_id = json.loads(state.read_text()).get('last_id', 0)
budget = 20
today = time.strftime('%Y-%m-%d')

while True:
    try:
        new_tweets = session.query(Tweet).filter(Tweet.id > last_id, Tweet.text != None, Tweet.text != '').order_by(Tweet.id).all()
        today_count = session.query(PipelineTask).filter(PipelineTask.task_type == 'analyze', PipelineTask.created_at >= today).count()
        for tw in new_tweets:
            if today_count >= budget: break
            existing = session.query(PipelineTask).filter(PipelineTask.task_type == 'filter', PipelineTask.payload.contains(str(tw.id))).first()
            if existing: continue
            t = PipelineTask(task_type='filter', status='pending', payload=json.dumps({{'action': 'filter_single', 'tweet_id': tw.id}}))
            session.add(t); today_count += 1
        if new_tweets:
            session.commit()
            last_id = new_tweets[-1].id
            state.write_text(json.dumps({{'last_id': last_id, 'updated': time.strftime('%Y-%m-%d %H:%M:%S')}}))
        session.close()
        time.sleep(30)
        session = db.get_session()
        today = time.strftime('%Y-%m-%d')
    except Exception as e:
        print(f'[DAEMON] {e}')
        session.rollback()
        break
""")
                proc = subprocess.Popen([sys.executable, "-c", inline], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                st.session_state.daemon_proc = proc
                st.session_state.daemon_started_at = _time.strftime("%H:%M:%S")
                st.session_state.daemon_log.append(f"{_time.strftime('%H:%M:%S')} Daemon 已启动 (PID={proc.pid})")

    with col2:
        if st.session_state.daemon_proc is not None:
            if st.button("⏸️ 停止"):
                st.session_state.daemon_proc.terminate()
                st.session_state.daemon_proc = None
                st.session_state.daemon_log.append(f"{_time.strftime('%H:%M:%S')} Daemon 手动停止")

    with col3:
        status = "🟢 运行中" if st.session_state.daemon_proc is not None else "⚫ 未启动"
        st.metric("状态", status)

    with col4:
        # 显示今日已创建任务数
        if st.session_state.daemon_proc is not None:
            from src.storage.database import db as _db
            from src.storage.models import PipelineTask as _PT
            _db.init_db()
            s = _db.get_session()
            today = _time.strftime("%Y-%m-%d")
            cnt = s.query(_PT).filter(_PT.task_type == "analyze", _PT.created_at >= today).count()
            s.close()
            st.metric("今日任务", f"{cnt}/20")

    # 日志展开
    if st.session_state.daemon_log:
        with st.expander("📋 日志", expanded=len(st.session_state.daemon_log) <= 3):
            for line in st.session_state.daemon_log[-10:]:
                st.text(line)


# ══════ Telegram 通知配置 ══════

TELEGRAM_CONFIG_PATH = Path("data/telegram_config.json")


def _render_telegram_config() -> None:
    """Telegram Bot 配置面板 — Step 4 #5 预警模块。"""
    import json as _json

    # 加载已有配置
    config = {}
    if TELEGRAM_CONFIG_PATH.exists():
        config = _json.loads(TELEGRAM_CONFIG_PATH.read_text(encoding="utf-8"))

    with st.expander("🔔 Telegram 预警通知配置", expanded=not bool(config.get("bot_token"))):
        col1, col2 = st.columns([2, 1])
        with col1:
            token = st.text_input("Bot Token", value=config.get("bot_token", ""), type="password",
                                   placeholder="123456:ABC-DEF1234ghIkl...")
        with col2:
            chat_id = st.text_input("Chat ID", value=config.get("chat_id", ""),
                                    placeholder="-1001234567890")

        if st.button("💾 保存配置"):
            new_config = {"bot_token": token, "chat_id": chat_id}
            TELEGRAM_CONFIG_PATH.write_text(_json.dumps(new_config, ensure_ascii=False, indent=2), encoding="utf-8")
            st.success("已保存 ✅")

        if config.get("bot_token"):
            st.caption(f"已配置 Bot: {config['bot_token'][:10]}... → Chat: {config.get('chat_id', '?')}")
            if st.button("🧪 发送测试消息"):
                msg = f"✅ 预警系统就绪\n时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                ok = _send_telegram(config["bot_token"], config["chat_id"], msg)
                if ok:
                    st.success("测试消息已发送")
                else:
                    st.error("发送失败，检查 Token/Chat ID")


def _send_telegram(token: str, chat_id: str, message: str) -> bool:
    """发送 Telegram 消息。返回是否成功。"""
    try:
        import urllib.request as _ur
        import json as _json
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = _json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
        req = _ur.Request(url, data=data, headers={"Content-Type": "application/json"})
        _ur.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def _get_sector_options() -> dict[str, list[str]]:
    """从 sector_map.json 构建板块选项。按 industry 细分类分组。"""
    import json as _j
    from pathlib import Path as _P
    from collections import defaultdict as _dd

    sp = _P("data/sector_map.json")
    if not sp.exists():
        st.warning("请先创建 data/sector_map.json")
        return {"未分类": []}

    d = _j.loads(sp.read_text(encoding="utf-8"))
    groups: dict[str, list[str]] = _dd(list)
    for ticker, v in d.items():
        sector = v.get("sector", "Other")
        industry = v.get("industry", "Other")
        label = f"{sector} / {industry}"
        groups[label].append(ticker)

    big_groups: dict[str, list[str]] = _dd(list)
    for ticker, v in d.items():
        big_groups[v.get("sector", "Other")].append(ticker)

    result = {}
    for k, v in sorted(groups.items(), key=lambda x: -len(x[1])):
        if len(v) >= 3:
            result[k] = sorted(v)
    for k, v in sorted(big_groups.items(), key=lambda x: -len(x[1])):
        if len(v) >= 3:
            result[f"【大类】{k}"] = sorted(v)

    return result


def _build_stock_pool(sector_tickers: list[str], custom: str) -> list[str]:
    """合并行业股票 + 手动加减。"""
    pool = set(sector_tickers)
    if custom:
        for part in custom.replace("，", ",").split(","):
            t = part.strip().upper()
            if t.startswith("-"):
                pool.discard(t[1:])
            elif t:
                pool.add(t)
    return sorted(pool)


def _run_role_picker_v2(analyst: str, sector: str, tickers: list[str], refresh_price: bool) -> str | None:
    """调用 LLM 生成选股方案。"""
    import json as _j
    from pathlib import Path as _P
    from src.ai.llm_client import chat
    import subprocess as _sp

    # 加载画像
    candidates = sorted(_P("data/pipeline").glob(f"{analyst}*portrait.md"))
    if not candidates:
        short = analyst.split("_")[0]
        candidates = sorted(_P("data/pipeline").glob(f"{short}*portrait.md"))
    portrait = candidates[-1].read_text(encoding="utf-8")[:3000] if candidates else "无画像"

    # 实时价格
    prices = {}
    if refresh_price:
        westock_js = str(_P.home() / ".workbuddy/plugins/marketplaces/cb_teams_marketplace/plugins/finance-data/skills/westock-data/scripts/index.js")
        for t in tickers[:25]:
            try:
                out = _sp.run(["node", westock_js, "quote", f"us{t}"], capture_output=True, text=True, timeout=10,
                              cwd=_P(westock_js).parent).stdout
                for line in out.split("\n"):
                    line = line.strip()
                    if not line.startswith("| us"):
                        continue
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 15:
                        prices[t] = {"price": parts[6], "pe": parts[15], "chg": parts[9]}
            except:
                pass

    # 基本面
    fundamentals = {}
    fp = _P("data/fundamental_cache.json")
    if fp.exists():
        fundamentals = _j.loads(fp.read_text(encoding="utf-8"))

    # 加载准确率
    acc_text = ""
    for afp in _P("data/accuracy").glob("*.json"):
        u = afp.stem.replace("_accuracy", "")
        d = _j.loads(afp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")
        if wr is not None:
            acc_text += f"- {u}: 30日胜率 {wr*100:.0f}%\n"

    # 股票池表
    rows = ["| Ticker | PE | ROE | 价格 | 涨跌 | 信号分 |"]
    rows.append("|--------|-----|------|------|------|--------|")
    for t in tickers[:25]:
        f = fundamentals.get(t, {})
        p = prices.get(t, {})
        pe = f"{f.get('pe_ratio','?'):.0f}" if f.get('pe_ratio') else "?"
        roe = f"{f.get('roe','?'):.0f}%" if f.get('roe') else "?"
        price = p.get("price", "?")
        chg = p.get("chg", "?")
        rows.append(f"| {t} | {pe} | {roe} | {price} | {chg} | ? |")

    prompt = f"""[Role]
你是 {analyst} 的投资决策模拟器。以下是他最新画像：

{portrait}

[准确率]
{acc_text}

[Task]
基于画像的投资框架，从 {sector} 行业股票池选 3-5 只最符合其理念的标的。
说明理由（引用画像维度），分配仓位（总和100%），给入场区间止损。

[{sector} 股票池]
{chr(10).join(rows)}

Output: 中文 Markdown。"""

    try:
        return chat(messages=[{"role": "user", "content": prompt}], role="analyzer", max_tokens=4096, temperature=0.5)
    except Exception:
        return None


if __name__ == "__main__":
    main()
