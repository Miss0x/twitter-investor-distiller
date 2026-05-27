"""统一配置管理模块。

从 .env 环境变量文件加载所有密钥和参数，以单例模式提供全项目统一的配置访问。

设计理念:
    - 懒加载: 首次访问配置项时才触发加载，避免导入时即执行 I/O
    - 单例模式: 全局唯一 Config 实例，所有模块共享同一份配置
    - 故障容错: dotenv 不可用时静默跳过，使用默认值继续运行

支持的配置项:
    - API 密钥: twitterapi_key, llm_api_key, polygon_key, cmc_key, telegram_bot_token
    - LLM 配置: llm_base_url, filter_model, analyzer_model, llm_temperature, llm_max_tokens, llm_timeout
    - Dashboard: dashboard_token（访问令牌）
    - 限流: rate_limit_per_minute

用法:
    from src.config import config
    print(config.llm_api_key)      # 首次访问自动加载
    print(config.filter_model)     # "gpt-4o-mini" (默认值)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# 项目根目录（src/config.py 的父目录）
PROJECT_ROOT = Path(__file__).parent.parent


class Config:
    """懒加载配置单例。

    通过重写 __getattr__ 实现属性访问时自动触发 _ensure_loaded()，
    只有在实际读取配置项时才会加载 .env 文件。

    Attributes:
        twitterapi_key: TwitterAPI.io 密钥（用于推文拉取）
        llm_base_url: LLM API 基础 URL（默认 OpenAI）
        llm_api_key: LLM API 密钥
        polygon_key: Polygon.io 股票数据密钥
        cmc_key: CoinMarketCap 加密货币数据密钥
        telegram_bot_token: Telegram Bot API Token
        dashboard_token: Web Dashboard 访问令牌
        filter_model: 推文过滤模型（默认 gpt-4o-mini）
        analyzer_model: 推文分析模型（默认 gpt-4o）
        llm_temperature: LLM 生成温度（默认 0.3）
        llm_max_tokens: LLM 最大输出 token 数（默认 4096）
        llm_timeout: LLM API 超时秒数（默认 120）
        rate_limit_per_minute: API 每分钟请求限流（默认 60）
    """

    def __init__(self):
        """初始化配置对象，标记未加载状态。"""
        self._loaded = False  # 懒加载标记

    def _ensure_loaded(self):
        """仅首次访问时执行一次加载，从 .env 文件读取所有配置项。

        加载顺序:
            1. 先尝试加载 dotenv 库
            2. 扫描项目根目录和 config/ 目录的 .env 文件
            3. 逐个读取环境变量并设置默认值
        """
        if self._loaded:
            return  # 已加载，跳过

        # ── 加载 dotenv 库（可选依赖） ──
        try:
            from dotenv import load_dotenv
            # 按优先级扫描两个位置
            for env_path in [PROJECT_ROOT / ".env", PROJECT_ROOT / "config" / ".env"]:
                if env_path.exists():
                    load_dotenv(env_path)  # 将 .env 中变量注入到 os.environ
                    break
        except ImportError:
            pass  # dotenv 不可用时跳过，依赖系统环境变量

        # ── API 密钥配置 ──
        self.twitterapi_key: str = os.getenv("TWITTERAPI_KEY", "")      # TwitterAPI.io 密钥
        self.llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")  # LLM 服务地址
        self.llm_api_key: str = os.getenv("LLM_API_KEY", "")            # LLM API 密钥
        self.polygon_key: str = os.getenv("POLYGON_KEY", "")            # Polygon.io 股票数据密钥
        self.cmc_key: str = os.getenv("CMC_KEY", "")                    # CoinMarketCap 密钥
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")  # Telegram Bot Token

        # ── Dashboard 认证 ──
        # 默认令牌用于本地开发，生产环境应通过环境变量覆盖
        self.dashboard_token: str = os.getenv("DASHBOARD_TOKEN", "twitter-distiller-2026")

        # ── LLM 模型与参数配置 ──
        self.filter_model: str = os.getenv("FILTER_MODEL", "gpt-4o-mini")    # 过滤阶段用轻量模型
        self.analyzer_model: str = os.getenv("ANALYZER_MODEL", "gpt-4o")     # 分析阶段用强模型
        self.llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))  # 温度（低=确定性高）
        self.llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))       # 最大输出token数
        self.llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "120"))              # API超时秒数

        # ── 速率限制 ──
        self.rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))  # 每分钟最大请求数

        self._loaded = True  # 标记已加载，后续访问直接返回

    def __getattr__(self, name: str) -> Any:
        """属性访问钩子：拦截非私有属性访问，自动触发懒加载。

        Args:
            name: 属性名

        Returns:
            属性值（若未设置则由 Python 抛出标准 AttributeError）
        """
        # 私有属性（以 _ 开头）直接访问，不触发加载
        if name.startswith("_"):
            return super().__getattribute__(name)
        # 首次访问任意公开属性时，先确保配置已加载
        self._ensure_loaded()
        return super().__getattribute__(name)


# 全局单例实例，项目所有模块通过此对象访问配置
config = Config()
