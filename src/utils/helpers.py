"""工具函数模块"""
import yaml
import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime


def load_yaml(file_path: str | Path) -> Dict[str, Any]:
    """加载 YAML 配置文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data: Dict[str, Any], file_path: str | Path) -> None:
    """保存数据到 YAML 文件"""
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


def load_json(file_path: str | Path) -> Dict[str, Any] | List[Any]:
    """加载 JSON 文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any] | List[Any], file_path: str | Path, indent: int = 2) -> None:
    """保存数据到 JSON 文件"""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在，不存在则创建"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_timestamp(dt: datetime = None) -> str:
    """格式化时间戳"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def clean_text(text: str) -> str:
    """清理文本"""
    if not text:
        return ""
    
    # 移除多余空白
    text = " ".join(text.split())
    
    # 移除特殊字符（保留基本标点）
    # 可以根据需要调整
    
    return text.strip()


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def get_file_size(file_path: str | Path) -> int:
    """获取文件大小（字节）"""
    return Path(file_path).stat().st_size


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"
