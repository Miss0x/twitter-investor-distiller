"""Single-user configuration center.

Reads and writes user_config.json in the project data directory.
Provides masked views for sensitive fields and applies config to runtime.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "llm": {"base_url": "", "api_key": "", "model": ""},
    "twitter": {"api_key": "", "api_secret": "", "access_token": "", "access_secret": ""},
    "telegram": {"bot_token": "", "chat_id": ""},
    "observations": [],
}


class ConfigManager:
    """Manage user configuration as a local JSON file."""

    def __init__(self, config_path: str | Path = "data/user_config.json") -> None:
        self.path = Path(config_path)

    def load(self) -> dict:
        if not self.path.exists():
            self._write(DEFAULT_CONFIG)
            return dict(DEFAULT_CONFIG)
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def save_section(self, section: str, values: dict) -> dict:
        config = self.load()
        current = config.get(section, {})
        if not isinstance(current, dict):
            current = {}
        current.update({k: v for k, v in values.items() if k in current or section in ("llm", "twitter", "telegram")})
        config[section] = current
        self._write(config)
        return config

    def add_observation(self, username: str) -> dict:
        config = self.load()
        obs = config.setdefault("observations", [])
        if username not in obs:
            obs.append(username)
        self._write(config)
        return config

    def remove_observation(self, username: str) -> dict:
        config = self.load()
        obs = config.get("observations", [])
        if username in obs:
            obs.remove(username)
        self._write(config)
        return config

    def load_masked(self) -> dict:
        config = self.load()
        masked = json.loads(json.dumps(config))
        for section in ("llm", "twitter", "telegram"):
            if section in masked and isinstance(masked[section], dict):
                for key in list(masked[section].keys()):
                    if any(sensitive in key.lower() for sensitive in ("api_key", "secret", "token")):
                        val = str(masked[section].get(key, ""))
                        if val and len(val) > 8:
                            masked[section][key] = val[:3] + "****" + val[-4:]
                        elif val:
                            masked[section][key] = "****"
        return masked

    def apply_llm_config(self) -> dict:
        config = self.load()
        llm = config.get("llm", {})
        base_url = llm.get("base_url") or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        api_key = llm.get("api_key") or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        model = llm.get("model") or os.getenv("CHAT_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4-turbo-preview"
        if api_key:
            os.environ["LLM_API_KEY"] = api_key
        return {"base_url": base_url, "api_key": api_key, "model": model}
