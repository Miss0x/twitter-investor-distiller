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

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "src" / "templates"


class Card(ABC):
    name: str = ""
    tab: str = "dashboard"
    endpoint: str = ""
    template: str = ""
    refresh: int = 0
    actions: dict[str, Any] = {}

    @abstractmethod
    def get_data(self, **params) -> dict[str, Any]:
        """获取卡片数据。params 来自 URL query string 或 POST body。"""
        ...

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

    def _render_html(self, data: dict[str, Any]) -> str:
        """子类可覆盖以自定义渲染。默认显示 JSON。"""
        import json as _json
        return f'<pre style="font-size:12px">{_json.dumps(data, indent=2, ensure_ascii=False)}</pre>'

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tab": self.tab,
            "endpoint": self.endpoint,
            "refresh": self.refresh,
            "has_actions": bool(self.actions),
        }
