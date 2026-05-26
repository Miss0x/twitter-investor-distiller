"""卡片基类 — 所有模块化卡片的统一接口。

每个卡片实现三个方法即可接入 dashboard：
    get_data() → dict     # 从数据源获取数据
    endpoint    → str     # API 端点路径
    template    → str     # Jinja2 模板文件名

可选：
    tab         → str     # 所属标签页: "dashboard" | "pipeline" | "insights"
    refresh     → int     # 自动刷新间隔(秒), 0=不自动刷新
    actions     → dict    # 支持的交互动作: {"action_name": handler_fn}
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


class Card(ABC):
    name: str = ""
    tab: str = ""
    endpoint: str = ""
    refresh: int = 0
    template: str = ""

    def get_data(self, **params) -> dict[str, Any]:
        return {}

    def _render_html(self, data: dict[str, Any]) -> str:
        return f"<pre>{data}</pre>"

    def render(self, data: dict[str, Any]) -> str:
        """渲染卡片 HTML。优先用 Jinja2 模板，否则用 _render_html。"""
        if self.template:
            try:
                import jinja2
                tpl_dir = Path(__file__).parent.parent / "templates" / "cards"
                env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(tpl_dir)))
                tpl = env.get_template(self.template)
                return tpl.render(**data)
            except Exception:
                pass
        return self._render_html(data)

    @staticmethod
    def handle_action(payload: dict) -> dict:
        return {"ok": False, "error": "action not supported"}
