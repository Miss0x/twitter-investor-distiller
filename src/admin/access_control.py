"""User access control — suspend/ban by IP prefix or username."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AccessControl:
    """Manage suspended/blocked users via a JSON blacklist file."""

    def __init__(self, path: str | Path = "data/access_control.json") -> None:
        self.path = Path(path)
        if not self.path.exists():
            self._write({"suspended": [], "blocked_ips": []})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def suspend(self, identifier: str, reason: str = "", admin: str = "admin") -> dict:
        """Suspend a user by username or IP prefix."""
        data = self._read()
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "identifier": identifier,
            "reason": reason,
            "suspended_by": admin,
            "suspended_at": now,
        }
        existing = [e for e in data["suspended"] if e["identifier"] != identifier]
        existing.append(entry)
        data["suspended"] = existing
        self._write(data)
        return {"ok": True, "suspended": identifier, "reason": reason}

    def unsuspend(self, identifier: str) -> dict:
        """Remove a suspension."""
        data = self._read()
        data["suspended"] = [e for e in data["suspended"] if e["identifier"] != identifier]
        self._write(data)
        return {"ok": True, "unsuspended": identifier}

    def is_suspended(self, identifier: str) -> bool:
        """Check if an identifier is currently suspended."""
        if not self.path.exists():
            return False
        data = self._read()
        return any(e["identifier"] == identifier for e in data.get("suspended", []))

    def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if an IP prefix is blocked."""
        if not self.path.exists():
            return False
        data = self._read()
        ip_prefix = ".".join(ip_address.split(".")[:2]) if "." in ip_address else ip_address
        for blocked in data.get("blocked_ips", []):
            if ip_prefix.startswith(blocked):
                return True
        return False

    def block_ip(self, ip_prefix: str, reason: str = "") -> dict:
        """Block an entire IP prefix (e.g. '192.168')."""
        data = self._read()
        if ip_prefix not in data.setdefault("blocked_ips", []):
            data["blocked_ips"].append(ip_prefix)
        self._write(data)
        return {"ok": True, "blocked": ip_prefix}

    def list_suspended(self) -> list[dict]:
        if not self.path.exists():
            return []
        return self._read().get("suspended", [])
