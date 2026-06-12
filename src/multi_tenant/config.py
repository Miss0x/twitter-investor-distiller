"""Per-user encrypted config manager with TTL caching.

Each user has their own encrypted config file.
Application code only sees decrypted values."""

from __future__ import annotations

import time
from pathlib import Path

from src.security.crypto import decrypt_config, derive_user_key, encrypt_config

DEFAULT_CONFIG = {
    "llm": {"base_url": "", "api_key": "", "model": ""},
    "twitter": {"provider": "official", "api_key": "", "api_secret": "", "access_token": "", "access_secret": "", "base_url": ""},
    "telegram": {"bot_token": "", "chat_id": ""},
    "observations": [],
}

CONFIG_CACHE_TTL = 300  # 5 minutes

_caches: dict[str, tuple[dict, float]] = {}
CONFIG_CACHE = _caches  # for test access


def _cache_get(tenant_id: str) -> dict | None:
    entry = _caches.get(tenant_id)
    if entry is None:
        return None
    data, expires = entry
    if time.time() > expires:
        _caches.pop(tenant_id, None)
        return None
    return data


def _cache_set(tenant_id: str, data: dict, ttl: float = CONFIG_CACHE_TTL) -> None:
    _caches[tenant_id] = (data, time.time() + ttl)


class PerUserConfig:
    """Per-user encrypted configuration manager."""

    def __init__(self, tenant_id: str, base_dir: str | Path = "data/tenants") -> None:
        self.tenant_id = tenant_id
        self._dir = Path(base_dir) / tenant_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "config.json"
        self._cache_key = f"config:{tenant_id}"
        # Derive encryption key from tenant identity + master key
        self._key = derive_user_key(tenant_id)

    def load(self) -> dict:
        """Load and decrypt config. Uses cache if available."""
        cached = _cache_get(self._cache_key)
        if cached is not None:
            return dict(cached)

        if not self._file.exists():
            data = dict(DEFAULT_CONFIG)
            self._save_encrypted(data)
        else:
            ct = self._file.read_text(encoding="utf-8")
            data = decrypt_config(ct, self._key)

        _cache_set(self._cache_key, data)
        return dict(data)

    def _save_encrypted(self, data: dict) -> None:
        ct = encrypt_config(data, self._key)
        self._file.write_text(ct, encoding="utf-8")

    def save_section(self, section: str, values: dict) -> dict:
        config = self.load()
        current = config.get(section, {})
        if not isinstance(current, dict):
            current = {}
        current.update(values)
        config[section] = current
        self._save_encrypted(config)
        _cache_set(self._cache_key, config)
        return config

    def add_observation(self, username: str) -> dict:
        config = self.load()
        obs = config.setdefault("observations", [])
        if username not in obs:
            obs.append(username)
        self._save_encrypted(config)
        _cache_set(self._cache_key, config)
        return config

    def remove_observation(self, username: str) -> dict:
        config = self.load()
        obs = config.get("observations", [])
        if username in obs:
            obs.remove(username)
        self._save_encrypted(config)
        _cache_set(self._cache_key, config)
        return config

    def load_masked(self) -> dict:
        """Return config with sensitive fields masked for display."""
        import json
        data = self.load()
        masked = json.loads(json.dumps(data))
        for section in ("llm", "twitter", "telegram"):
            if section in masked and isinstance(masked[section], dict):
                for key in ("api_key", "api_secret", "token", "bot_token"):
                    val = str(masked[section].get(key, ""))
                    if val and len(val) > 8:
                        masked[section][key] = val[:3] + "****" + val[-4:]
                    elif val:
                        masked[section][key] = "****"
        return masked

    def apply_llm_config(self) -> dict:
        """Apply LLM config to runtime environment and reload chat engine."""
        import os
        config = self.load()
        llm = config.get("llm", {})
        base_url = llm.get("base_url") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1"
        api_key = llm.get("api_key") or os.getenv("LLM_API_KEY") or ""
        model = llm.get("model") or os.getenv("CHAT_MODEL") or "gpt-4-turbo-preview"
        if api_key:
            os.environ["LLM_API_KEY"] = api_key
        if base_url:
            os.environ["LLM_BASE_URL"] = base_url
        if model:
            os.environ["CHAT_MODEL"] = model
        # Reload global chat engine singleton if loaded
        try:
            from src.interfaces.web_api import _chat_engine
            if _chat_engine is not None:
                _chat_engine.reload_config()
        except ImportError:
            pass
        return {"base_url": base_url, "api_key": api_key, "model": model}
