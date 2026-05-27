"""环境变量加载工具模块。

功能:
    - 按优先级自动加载项目中的 .env 文件
    - 优先级: 先加载项目根目录 .env，再加载 config 目录下的 .env（后者不覆盖前者）

用法:
    from src.utils.env import load_project_env
    load_project_env()
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_project_env() -> None:
    """按优先级加载项目环境变量文件。

    加载顺序:
        1. 项目根目录下的 .env 文件
        2. config/ 目录下的 .env 文件

    注意:
        - 使用 override=False，后加载的文件不会覆盖已存在的环境变量
        - 这意味着根目录 .env 的变量优先级最高
    """
    # 获取项目根目录（src/utils/env.py 的上两级）
    project_root = Path(__file__).parent.parent.parent
    root_env = project_root / ".env"       # 根目录 .env 文件
    config_env = project_root / "config" / ".env"  # config 目录下的 .env 文件

    # 按顺序加载，override=False 确保先加载的优先
    if root_env.exists():
        load_dotenv(root_env, override=False)
    if config_env.exists():
        load_dotenv(config_env, override=False)
