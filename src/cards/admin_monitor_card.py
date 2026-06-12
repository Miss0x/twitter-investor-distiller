"""Admin monitoring card — usage stats, activity log, privacy-safe."""

from __future__ import annotations

from src.cards.base import Card
from src.cards import register
from src.admin.activity import ActivityTracker

ACTION_LABELS = {
    "page_view": "浏览", "config_change": "修改配置", "task_execute": "执行任务",
    "task_seed": "扫描任务", "task_skip": "跳过任务", "task_retry": "重试任务",
    "governance_acknowledge": "接受风险", "governance_revoke": "撤销接受",
    "chat_query": "AI 问答", "observation_add": "添加观察", "observation_remove": "移除观察",
    "login": "登录", "logout": "登出",
}


@register
class AdminMonitorCard(Card):
    """系统监控面板 — 用户活动统计、操作分布、每日趋势、最近记录。"""

    name = "admin_monitor"
    display_title = "系统监控"
    template = "admin_monitor.html"

    def get_data(self) -> dict:
        tracker = ActivityTracker()
        stats = tracker.stats(days=7)

        actions = stats.get("actions_by_type", {})
        total = stats.get("total_events", 0) or 1
        top_actions = [
            {
                "label": ACTION_LABELS.get(k, k),
                "count": v,
                "pct": round(v / total * 100, 1),
            }
            for k, v in sorted(actions.items(), key=lambda x: -x[1])[:8]
        ]

        tabs = stats.get("tabs_by_usage", {})
        top_tab = max(tabs.items(), key=lambda x: x[1]) if tabs else ("-", 0)

        hourly = stats.get("hourly_activity", {})
        peak_hour = max(hourly.items(), key=lambda x: x[1])[0] if hourly else "-"

        dailies = stats.get("daily_totals", {})
        daily_max = max(dailies.values()) if dailies else 1
        daily_bars = [
            {
                "label": k[-5:],
                "count": v,
                "pct": round(v / daily_max * 100, 1),
            }
            for k, v in sorted(dailies.items())[-7:]
        ]

        recent_raw = tracker.query(limit=20)
        recent_events = [
            {
                "action_label": ACTION_LABELS.get(e.get("action", ""), e.get("action", "")),
                "path": e.get("path", ""),
                "tab": e.get("tab", ""),
                "time_short": (e.get("timestamp", "")[-8:] or "")[:8],
            }
            for e in recent_raw[:12]
        ]

        return {
            "total_events": total,
            "unique_ip_prefixes": stats.get("unique_ip_prefixes", 0),
            "top_tab_count": top_tab[1],
            "top_tab_label": top_tab[0],
            "peak_hour": peak_hour + ":00",
            "top_actions": top_actions,
            "daily_max": daily_max,
            "daily_bars": daily_bars,
            "recent_events": recent_events,
        }
