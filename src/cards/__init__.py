"""
卡片注册表（Card Registry）— 所有模块化页面卡片的统一入口与管理系统。
=====================================================================

设计意图
--------
整个 Dashboard 由多个独立"卡片"组成。本模块维护一个全局注册表 `CARDS`，
Dashboard 启动时遍历 CARDS，按 `tab` 属性分组渲染，并将卡片挂载到对应路由。

注册机制
--------
新增卡片只需：
  1. 在卡片模块中定义 Card 子类
  2. 用 @register 装饰器注册
  3. 在本文件末尾添加 `from . import xxx` 导入触发注册

关键数据结构
------------
CARDS: list[Card]   全局卡片实例列表，按注册顺序排列
register()          装饰器，实例化卡片并加入 CARDS
get_cards_by_tab(tab)   按标签页筛选卡片
get_card(name)          按名称查找单个卡片
"""
from __future__ import annotations

from .base import Card
from .cards_config import CARD_CONFIG, apply_card_config

# ── 全局卡片注册表 ──
# 存储所有已注册卡片实例的列表，Dashboard 遍历此列表进行路由挂载和页面渲染
CARDS: list[Card] = []


def register(card_cls):
    """
    卡片注册装饰器。

    用法:
        @register
        class MyCard(Card):
            name = "my_card"
            ...

    行为:
        1. 从 CARD_CONFIG 中心配置注入元数据
        2. 校验 template 和 _render_html() 互斥（规则二）
        3. 实例化 card_cls 并追加到全局 CARDS 列表
        4. 返回原始类

    参数:
        card_cls: Card 子类（非实例），必须可无参实例化
    """
    instance = card_cls()

    # ── 从中心配置注入元数据 ──
    apply_card_config(instance)

    # ── 规则二：template 和 _render_html 互斥校验 ──
    has_template = bool(instance.template)
    has_custom_render = (type(instance)._render_html != Card._render_html)
    if has_template and has_custom_render:
        raise ValueError(
            f"Card '{instance.name}' has both template='{instance.template}' "
            f"and a custom _render_html(). "
            f"They are mutually exclusive (规则二). Remove one from CARD_CONFIG "
            f"or the card class."
        )

    CARDS.append(instance)
    return card_cls


def get_cards_by_tab(tab: str) -> list[Card]:
    """
    按标签页获取卡片列表。

    用于 Dashboard 渲染时按分组排列卡片:
      - "dashboard"  → 主仪表盘
      - "pipeline"   → 流水线操作
      - "insights"   → 分析洞察
      - "portraits"  → 分析师画像

    参数:
        tab: 标签页标识符

    返回:
        该标签页下所有卡片实例的列表（按注册顺序）
    """
    return [c for c in CARDS if c.tab == tab]


def get_card(name: str) -> Card | None:
    """
    按名称查找单个卡片实例。

    用于 API 路由分发时匹配请求到对应卡片:
      GET /api/{card.endpoint} → 调用 card.get_data()
      POST /api/{card.endpoint} → 调用 card.handle_action()

    参数:
        name: 卡片 name 属性值（唯一标识）

    返回:
        Card 实例，未找到返回 None
    """
    for c in CARDS:
        if c.name == name:
            return c
    return None


# ── 导入所有卡片模块以触发 @register 装饰器 ──
# 每个 import 会执行模块顶层代码，从而运行 @register 将卡片实例注入 CARDS
# noqa 注释抑制 linter 的"未使用导入"警告
from . import chat_card     # noqa: E402, F401   — 智能问答入口
from . import accuracy       # noqa: E402, F401   — 分析准确率面板
from . import consensus      # noqa: E402, F401   — 多分析师共识信号
from . import rotation       # noqa: E402, F401   — 板块轮动热点
from . import anomaly        # noqa: E402, F401   — 异常检测窗口
from . import network        # noqa: E402, F401   — 关联网络图
from . import system_status  # noqa: E402, F401   — 系统统计概览
from . import interactive_cards  # noqa: E402, F401  — 交互卡片组（Daemon/Telegram/角色/持仓）
from . import pipeline_control   # noqa: E402, F401  — API 采集状态面板
from . import tool_cards     # noqa: E402, F401   — 工具卡片组（拉取控制/画像浏览）
from . import functional_cards  # noqa: E402, F401  — 功能卡片组（资产别名/加密货币/脚本/时间线）
from . import pipeline_execute  # noqa: E402, F401  — 流水线执行面板 + 画像生成
from . import governance_cards  # noqa: E402, F401  — 信号治理卡片组（质量门禁/风险提示/多角色评审/发布审核）
from . import config_center_card  # noqa: E402, F401  — 用户配置中心（LLM / Twitter / Telegram / 观察对象）
from . import valuation_card  # noqa: E402, F401  — 估值工具（DCF/Comps/尽调清单）
from . import financial_cards  # noqa: E402, F401  — 财报日历 + 价格预警
