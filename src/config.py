"""统一配置管理 — 从 .env + yaml 加载，全项目单例。

用法:
    from src.config import config
    print(config.twitterapi_key)
    print(config.llm_api_key)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent


class Config:
    """懒加载配置单例。"""

    def __init__(self):
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        # .env
        try:
            from dotenv import load_dotenv
            for env_path in [PROJECT_ROOT / ".env", PROJECT_ROOT / "config" / ".env"]:
                if env_path.exists():
                    load_dotenv(env_path)
                    break
        except ImportError:
            pass

        self.twitterapi_key: str = os.getenv("TWITTERAPI_KEY", "")
        self.llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.llm_api_key: str = os.getenv("LLM_API_KEY", "")
        self.polygon_key: str = os.getenv("POLYGON_KEY", "")
        self.cmc_key: str = os.getenv("CMC_KEY", "")
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

        # dashboard auth
        self.dashboard_token: str = os.getenv("DASHBOARD_TOKEN", "twitter-distiller-2026")

        # 默认模型
        self.filter_model: str = os.getenv("FILTER_MODEL", "gpt-4o-mini")
        self.analyzer_model: str = os.getenv("ANALYZER_MODEL", "gpt-4o")
        self.llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
        self.llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))
        self.llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "120"))

        # rate limiting
        self.rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

        self._loaded = True

    def __getattr__(self, name: str) -> Any:
        self._ensure_loaded()
        return super().__getattribute__(name)


config = Config()
