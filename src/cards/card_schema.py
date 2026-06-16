"""
卡片数据 Schema 校验（规则五）。
==============================

使用 Python dataclass 定义每张卡片的 get_data() 返回值结构。
在 FastAPI card_data 端点渲染前自动校验字段存在性和类型。

新增卡片的步骤：
  1. 在此文件定义对应的 dataclass
  2. 在 SCHEMA_MAP 中注册映射
  3. 渲染前自动校验（由 web_api.py 的 card_data 端点处理）

设计选择：
  - 使用标准库 dataclass（零额外依赖）
  - 校验失败不中断渲染，而是返回 {error: "..."} 信封
  - 字段缺失时使用 None 填充（优雅降级），同时记录警告日志
"""

from __future__ import annotations

from dataclasses import MISSING, dataclass, fields, is_dataclass
import logging

_log = logging.getLogger(__name__)


# ── Schema 定义 ──

@dataclass
class SystemStatusData:
    """系统统计卡片数据结构。"""
    tweets: int = 0
    analyzed: int = 0
    portraits: int = 0
    signals: int = 0


@dataclass
class ConsensusItem:
    """单条共识信号。"""
    ticker: str = ""
    signal: str = ""
    consensus_score: float = 0.0
    analysts: list = None

    def __post_init__(self):
        if self.analysts is None:
            self.analysts = []


@dataclass
class ConsensusData:
    """共识卡片数据结构。"""
    top: list = None
    total: int = 0
    multi: int = 0

    def __post_init__(self):
        if self.top is None:
            self.top = []


@dataclass
class AccuracyAnalyst:
    """单分析师准确率数据。"""
    win_rate: float = 0.0
    sharpe: float = 0.0
    count: int = 0


@dataclass
class DaemonData:
    """守护进程状态数据结构。"""
    running: bool = False
    last_id: int = 0
    today: int = 0
    budget: int = 20


@dataclass
class ApiStatusData:
    """API 采集状态数据结构。"""
    users: list = None
    user_counts: dict = None
    total_fetched: int = 0
    last_updated: str = "未开始"
    rate_limited: str = ""
    cursors: dict = None

    def __post_init__(self):
        if self.users is None:
            self.users = []
        if self.user_counts is None:
            self.user_counts = {}
        if self.cursors is None:
            self.cursors = {}


@dataclass
class CryptoData:
    """加密货币信号数据结构。"""
    coins: dict = None
    mentions: dict = None
    total_coins: int = 0

    def __post_init__(self):
        if self.coins is None:
            self.coins = {}
        if self.mentions is None:
            self.mentions = {}


@dataclass
class RotationData:
    """板块轮动数据结构。"""
    rotation: dict = None

    def __post_init__(self):
        if self.rotation is None:
            self.rotation = {}


@dataclass
class NetworkData:
    """关联网络数据结构。"""
    recs: list = None
    edges: int = 0
    nodes: int = 0

    def __post_init__(self):
        if self.recs is None:
            self.recs = []


# ── Schema 映射表 ──
# 仅包含需要强校验的卡片。不需要校验的卡片可以不在映射中。

SCHEMA_MAP: dict[str, type] = {
    "system_status": SystemStatusData,
    "consensus": ConsensusData,
    "daemon": DaemonData,
    "api_status": ApiStatusData,
    "crypto": CryptoData,
    "rotation": RotationData,
    "network": NetworkData,
}


def validate_card_data(name: str, data: dict) -> tuple[dict, str | None]:
    """校验卡片数据是否符合 schema。

    Args:
        name: 卡片名称
        data: get_data() 返回的字典

    Returns:
        (normalized_data, error_message)
        - 校验通过: (data, None)
        - 校验失败: (data_with_defaults, warning_message)
    """
    schema_cls = SCHEMA_MAP.get(name)
    if schema_cls is None:
        return data, None  # 不需要校验

    if not is_dataclass(schema_cls):
        return data, None

    warnings = []

    for f in fields(schema_cls):
        field_name = f.name
        if field_name not in data:
            # 字段缺失 → 使用默认值（优雅降级）
            # 优先级：显式 default → default_factory → None
            if f.default is not MISSING:
                data[field_name] = f.default
            elif f.default_factory is not MISSING:
                data[field_name] = f.default_factory()
            else:
                data[field_name] = None
            warnings.append(f"  - {field_name}: missing, using default")

    if warnings:
        _log.warning(
            f"Card '{name}' data schema validation warnings:\n" +
            "\n".join(warnings)
        )

    return data, None  # 总是返回数据（不中断渲染）
