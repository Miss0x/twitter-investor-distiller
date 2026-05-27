"""通用工具函数模块。

提供项目各模块共享的基础工具函数，包括:
    - YAML/JSON 文件读写（配置文件的加载与保存）
    - 文件系统操作（目录创建、文件大小获取）
    - 文本处理（清理、截断）
    - 时间戳格式化

这些函数是纯工具性的，不依赖项目其他模块。
"""
import yaml
import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime


def load_yaml(file_path: str | Path) -> Dict[str, Any]:
    """加载 YAML 配置文件。

    Args:
        file_path: YAML 文件的路径

    Returns:
        解析后的 YAML 内容字典

    Raises:
        FileNotFoundError: 文件不存在时抛出
        yaml.YAMLError: YAML 解析失败时抛出
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)  # safe_load 避免执行任意 Python 代码


def save_yaml(data: Dict[str, Any], file_path: str | Path) -> None:
    """保存数据到 YAML 文件。

    Args:
        data: 要保存的字典数据
        file_path: 目标文件路径

    注意:
        - allow_unicode=True: 支持中文字符正常输出
        - default_flow_style=False: 使用块样式，更易读
    """
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def load_json(file_path: str | Path) -> Dict[str, Any] | List[Any]:
    """加载 JSON 文件。

    Args:
        file_path: JSON 文件路径

    Returns:
        解析后的 JSON 数据（字典或列表）

    Raises:
        json.JSONDecodeError: JSON 格式错误时抛出
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any] | List[Any], file_path: str | Path, indent: int = 2) -> None:
    """保存数据到 JSON 文件。

    Args:
        data: 要保存的数据（字典或列表）
        file_path: 目标文件路径
        indent: JSON 缩进空格数（默认 2，便于阅读）
    """
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)  # ensure_ascii=False 保留中文


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在，不存在则递归创建。

    Args:
        path: 目录路径

    Returns:
        Path 对象（链式调用便利）

    Example:
        ensure_dir("data/output").joinpath("result.json")
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)  # parents=True 递归创建，exist_ok=True 已存在不报错
    return path


def format_timestamp(dt: datetime = None) -> str:
    """格式化时间戳为统一格式字符串。

    Args:
        dt: datetime 对象，默认为当前时间

    Returns:
        格式为 "YYYY-MM-DD HH:MM:SS" 的字符串
    """
    if dt is None:
        dt = datetime.now()  # 默认使用当前时间
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def clean_text(text: str) -> str:
    """清理文本：移除多余空白字符。

    Args:
        text: 原始文本

    Returns:
        清理后的文本（合并连续空白为单个空格，去除首尾空白）

    Note:
        保留基本标点符号，不会篡改内容语义
    """
    if not text:
        return ""

    # 将所有连续空白字符（空格、换行、制表符等）合并为单个空格
    text = " ".join(text.split())

    return text.strip()


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断文本到指定长度，超出部分用 suffix 替代。

    Args:
        text: 原始文本
        max_length: 最大长度（包括 suffix）
        suffix: 截断后缀（默认 "..."）

    Returns:
        截断后的文本，长度不超过 max_length

    Example:
        truncate_text("这是一段很长的文本", 7) → "这是一段..."
    """
    if len(text) <= max_length:
        return text
    # 预留 suffix 的空间再截断
    return text[:max_length - len(suffix)] + suffix


def get_file_size(file_path: str | Path) -> int:
    """获取文件大小。

    Args:
        file_path: 文件路径

    Returns:
        文件大小（字节数）
    """
    return Path(file_path).stat().st_size


def format_file_size(size_bytes: int) -> str:
    """将字节数格式化为人类可读的文件大小。

    Args:
        size_bytes: 字节数

    Returns:
        格式化的字符串，如 "1.50 MB"

    Example:
        format_file_size(1536) → "1.50 KB"
        format_file_size(1048576) → "1.00 MB"
    """
    # 按 B → KB → MB → GB → TB 顺序尝试
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0  # 除以 1024 升一级单位
    return f"{size_bytes:.2f} TB"
