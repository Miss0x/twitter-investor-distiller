"""日志配置模块。

基于 Loguru 的统一日志配置，提供:
    - 控制台彩色日志输出（带时间戳、模块名、行号）
    - 按日轮转的应用日志文件（保留 30 天）
    - 独立的错误日志文件（保留 90 天）

日志级别:
    - 通过环境变量 LOG_LEVEL 控制（默认 INFO）
    - 日志文件默认输出到 ./logs 目录（可通过 LOG_PATH 配置）

用法:
    from src.utils.logger import logger
    logger.info("这是一条日志")
    logger.error("发生错误")
"""
import os
import sys
from pathlib import Path

# 导入 Loguru 的 logger 对象
from loguru import logger

# 先加载环境变量（日志配置需要 LOG_LEVEL/LOG_PATH）
from src.utils.env import load_project_env

load_project_env()


# ── 日志级别与路径配置 ──
# 从环境变量读取，未设置时使用默认值
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")       # 日志级别
LOG_PATH = Path(os.getenv("LOG_PATH", "./logs"))  # 日志文件目录

# 确保日志目录存在
LOG_PATH.mkdir(parents=True, exist_ok=True)

# 移除 Loguru 默认的控制台处理器
logger.remove()

# ── 控制台输出 ──
# 彩色格式，方便开发时实时查看日志
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
           "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
           "<level>{message}</level>",
    level=LOG_LEVEL,
    colorize=True,  # 启用终端彩色输出
)

# ── 应用日志文件（按日轮转） ──
# 记录所有级别日志，每天午夜自动创建新文件
logger.add(
    LOG_PATH / "app_{time:YYYY-MM-DD}.log",
    rotation="00:00",      # 每天午夜 00:00 轮转
    retention="30 days",    # 保留最近 30 天的日志文件
    level=LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)

# ── 错误日志文件（按日轮转，长期保留） ──
# 仅记录 ERROR 及以上级别，用于故障排查和审计
logger.add(
    LOG_PATH / "error_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="90 days",    # 错误日志保留更长时间（90 天）
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)

# 导出配置好的 logger 对象供其他模块使用
__all__ = ["logger"]
