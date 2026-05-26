"""环境变量加载工具。"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_project_env() -> None:
    """按优先级加载项目环境变量。"""
    project_root = Path(__file__).parent.parent.parent
    root_env = project_root / ".env"
    config_env = project_root / "config" / ".env"

    if root_env.exists():
        load_dotenv(root_env, override=False)
    if config_env.exists():
        load_dotenv(config_env, override=False)
