"""Activity tracking for admin monitoring.

Records user actions without collecting PII.
Uses append-only JSONL files for lightweight storage.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ActivityAction = Literal[
    "page_view",
    "config_change",
    "task_execute",
    "task_seed",
    "task_skip",
    "task_retry",
    "governance_acknowledge",
    "governance_revoke",
    "chat_query",
    "observation_add",
    "observation_remove",
    "login",
    "logout",
    "user_suspended",
    "user_reactivated",
]

SAFE_FIELDS = {
    "action", "path", "tab", "card", "item_count", "signal_id",
    "ticker", "gap_code", "task_type", "username", "ip_prefix",
    "user_agent_short", "timestamp",
}


def _ip_hash(ip: str) -> str:
    """One-way hash IP for privacy — allows counting unique visitors without storing raw IP."""
    return hashlib.sha256(f"salt-activity-{ip}".encode()).hexdigest()[:12]


def _ua_short(ua: str) -> str:
    ua = (ua or "").strip()[:120]
    for kw in ("Chrome/", "Firefox/", "Safari/", "Edg/"):
        if kw in ua:
            return ua[:ua.index(kw) + 20]
    return ua[:40]


def _ip_prefix(ip: str) -> str:
    """Store only first 2 octets of IP, e.g. '192.168'."""
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join(parts[:2])
    return "unknown"


class ActivityTracker:
    """Append-only activity logger. No PII collected."""

    def __init__(self, base_dir: str | Path = "data/activity") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _today_path(self) -> Path:
        return self.base_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"

    def log(
        self,
        action: ActivityAction,
        *,
        ip_address: str = "",
        user_agent: str = "",
        path: str = "",
        tab: str = "",
        card: str = "",
        item_count: int = 0,
        signal_id: str = "",
        ticker: str = "",
        gap_code: str = "",
        task_type: str = "",
        username: str = "",
    ) -> None:
        entry = {
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip_prefix": _ip_prefix(ip_address),
            "user_agent_short": _ua_short(user_agent),
        }
        if path:
            entry["path"] = path
        if tab:
            entry["tab"] = tab
        if card:
            entry["card"] = card
        if item_count:
            entry["item_count"] = item_count
        if signal_id:
            entry["signal_id"] = signal_id
        if ticker:
            entry["ticker"] = ticker
        if gap_code:
            entry["gap_code"] = gap_code
        if task_type:
            entry["task_type"] = task_type
        if username:
            entry["username"] = username

        with self._today_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def query(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        action: str | None = None,
        tab: str | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Query activity log with optional filters."""
        results: list[dict] = []
        files = sorted(self.base_dir.glob("*.jsonl"), reverse=True)

        for fp in files:
            date_str = fp.stem
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            try:
                for line in fp.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if action and entry.get("action") != action:
                        continue
                    if tab and entry.get("tab") != tab:
                        continue
                    results.append(entry)
                    if len(results) >= limit:
                        return results
            except (json.JSONDecodeError, OSError):
                continue

        return results

    def stats(self, *, days: int = 7) -> dict:
        """Compute aggregate usage statistics for the last N days."""
        from collections import Counter

        cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        actions_counter: Counter = Counter()
        tabs_counter: Counter = Counter()
        hourly_counter: Counter = Counter()
        daily_total: dict[str, int] = {}
        unique_ips: set = set()

        for fp in sorted(self.base_dir.glob("*.jsonl")):
            if fp.stem < cutoff[:10]:
                continue
            try:
                for line in fp.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    actions_counter[entry.get("action", "unknown")] += 1
                    if entry.get("tab"):
                        tabs_counter[entry["tab"]] += 1
                    ts = entry.get("timestamp", "")
                    if ts:
                        hour = ts[11:13] if len(ts) >= 13 else "unknown"
                        hourly_counter[hour] += 1
                    date_key = fp.stem
                    daily_total[date_key] = daily_total.get(date_key, 0) + 1
                    if entry.get("ip_prefix"):
                        unique_ips.add(entry["ip_prefix"])
            except (json.JSONDecodeError, OSError):
                continue

        return {
            "total_events": sum(actions_counter.values()),
            "actions_by_type": dict(actions_counter.most_common(20)),
            "tabs_by_usage": dict(tabs_counter.most_common(10)),
            "hourly_activity": dict(sorted(hourly_counter.items())),
            "daily_totals": dict(sorted(daily_total.items())),
            "unique_ip_prefixes": len(unique_ips),
            "period_days": days,
        }
