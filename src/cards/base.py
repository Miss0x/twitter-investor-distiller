"""
卡片基类（Card Base）— 所有模块化卡片的统一抽象接口。
========================================================

设计思想
--------
Dashboard 由多个独立"卡片"组成，每张卡片负责一个功能模块的展示与交互。
所有卡片继承 `Card` 抽象基类，只需覆写必要方法即可接入 dashboard。

子类必须提供：
    name      → str   卡片唯一标识名，用于 API 路由匹配和查找
    endpoint  → str   API 端点路径，如 "/api/system_status"，
                      前端通过 GET {endpoint} 获取数据、POST {endpoint} 触发动作
    template  → str   Jinja2 模板文件名（位于 src/templates/cards/），
                      优先级高于 _render_html()

子类可选覆写：
    tab       → str   所属标签页，决定卡片出现在哪个页面分组：
                          "dashboard"  — 主仪表盘（系统状态、采集、守护进程等）
                          "pipeline"   — 流水线操作（扫描新内容、执行面板等）
                          "insights"   — 分析洞察（信号、板块、网络等）
                          "portraits"  — 分析师画像
    refresh   → int   自动刷新间隔（秒），前端轮询 get_data() 的频率。
                      0 表示不自动刷新（静态卡片）。
    get_data()        数据获取方法，接收前端查询参数，返回 dict 供模板或 _render_html 使用
    _render_html()    内联 HTML 生成（无 Jinja2 模板时使用）
    handle_action()   处理前端 POST 动作（如按钮点击）

数据流
------
前端轮询 → GET {endpoint} → get_data(**params) → render(data) → HTML 片段 → 替换卡片 DOM
用户交互 → POST {endpoint} → handle_action(payload) → JSON 响应
"""
from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Any

# 模板目录根路径，指向 src/templates/
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class Card(ABC):
    """
    卡片抽象基类。

    每个子类代表 Dashboard 上的一个功能模块，
    定义自己的数据源（get_data）、渲染方式（_render_html 或 template）、
    和交互处理（handle_action）。
    """

    # ── 属性说明 ──
    name: str = ""
    # ↑ 卡片唯一标识名，用于 /api 端点注册和卡片查找

    tab: str = ""
    # ↑ 所属标签页标识符 (如 "signals", "decisions", "data")

    tab_label: str = ""
    # ↑ 标签页的人类可读名称 (如 "今日信号", "投资决策")

    tab_order: int = 99
    # ↑ 标签页排序（数字越小越靠左），所有同 tab 的卡片共享此值

    order: int = 99
    # ↑ 标签页内卡片排序（数字越小越靠前）

    is_headline: bool = False
    # ↑ 是否使用头条高亮样式（橙色渐变背景 + 加粗标题）

    span_full: bool = False
    # ↑ 是否占满整行（grid-column: 1 / -1）

    endpoint: str = ""
    # ↑ API 端点路径，如 "/api/system_status"，
    #   前端通过 fetch(endpoint) 获取卡片数据

    refresh: int = 0
    # ↑ 自动刷新间隔（秒），0 = 不自动刷新

    template: str = ""
    # ↑ Jinja2 模板文件名（位于 src/templates/cards/），
    #   非空时优先用模板渲染，否则走 _render_html()

    display_title: str = ""
    # ↑ 用户可见的中文标题（命名优化层），由 CARD_DISPLAY 注入。
    #   仅用于显示，不影响 name 标识符/路由/文件名。

    subtitle: str = ""
    # ↑ 一句话功能说明，由 CARD_DISPLAY 注入。
    #   显示在卡片标题下方，帮助用户理解该模块的用途。

    # ── 方法说明 ──

    def get_data(self, **params) -> dict[str, Any]:
        """
        获取卡片数据。

        参数:
            **params: 前端传来的查询参数（如 username, window 等）

        返回:
            dict: 卡片数据，会传入 render() 或 Jinja2 模板
                  默认返回空字典，子类应覆写此方法从数据库/文件获取数据
        """
        return {}

    def _render_html(self, data: dict[str, Any]) -> str:
        """
        内联生成 HTML 片段（无模板时使用）。

        参数:
            data: get_data() 返回的数据字典

        返回:
            str: 可嵌入 dashboard 的 HTML 片段（非完整页面）
                 默认仅以 <pre> 展示原始数据，子类应覆写以生成正式 UI
        """
        return f"<pre>{data}</pre>"

    def render(self, data: dict[str, Any]) -> str:
        """
        渲染卡片为 HTML 字符串。

        优先级:
            1. 如果 self.template 非空 → 使用 Jinja2 模板渲染
            2. 否则 → 调用 self._render_html(data) 内联生成

        参数:
            data: get_data() 返回的数据字典

        返回:
            str: 最终 HTML 片段，会被插入到 dashboard 对应卡片槽位
        """
        if self.template:
            try:
                import jinja2
                tpl_dir = Path(__file__).parent.parent / "templates" / "cards"
                env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(tpl_dir)))
                tpl = env.get_template(self.template)
                return tpl.render(**data)
            except Exception:
                pass  # 模板加载失败时降级到 _render_html
        return self._render_html(data)

    @staticmethod
    def handle_action(payload: dict) -> dict:
        """
        处理前端 POST 动作（如按钮点击、参数提交）。

        参数:
            payload: 前端 JSON body，如 {"action": "start", "username": "xxx"}

        返回:
            dict: JSON 响应体，默认返回 error
                  子类应覆写以支持具体操作，如:
                  {"ok": True}、{"ok": False, "error": "..."} 等
        """
        return {"ok": False, "error": "action not supported"}

    def to_dict(self) -> dict:
        """
        将卡片元数据序列化为 dict，供 /cards/meta API 返回。

        返回:
            {
                "name": "consensus",
                "tab": "signals",
                "tab_label": "今日信号",
                "tab_order": 1,
                "order": 1,
                "is_headline": true,
                "span_full": false,
                "refresh": 600,
                "endpoint": "/cards/consensus"
            }
        """
        return {
            "name": self.name,
            "tab": self.tab,
            "tab_label": self.tab_label,
            "tab_order": self.tab_order,
            "order": self.order,
            "is_headline": getattr(self, "is_headline", False),
            "span_full": getattr(self, "span_full", False),
            "refresh": getattr(self, "refresh", 0),
            "display_title": getattr(self, "display_title", ""),
            "subtitle": getattr(self, "subtitle", ""),
            "endpoint": f"/cards/{self.name}",
        }
