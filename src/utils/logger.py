"""日志配置模块"""
import os
import sys
from pathlib import Path

from loguru import logger

from src.utils.env import load_project_env

# 加载环境变量
load_project_env()


# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_PATH = Path(os.getenv("LOG_PATH", "./logs"))

# 创建日志目录
LOG_PATH.mkdir(parents=True, exist_ok=True)

# 移除默认处理器
logger.remove()

# 添加控制台输出
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=LOG_LEVEL,
    colorize=True,
)

# 添加文件输出 - 所有日志
logger.add(
    LOG_PATH / "app_{time:YYYY-MM-DD}.log",
    rotation="00:00",  # 每天午夜轮转
    retention="30 days",  # 保留30天
    level=LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)

# 添加错误日志文件
logger.add(
    LOG_PATH / "error_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="90 days",  # 错误日志保留更久
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)

# 导出配置好的 logger
__all__ = ["logger"]
