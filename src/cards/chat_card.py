"""智能问答卡片。"""
from __future__ import annotations

import html

from src.cards.base import Card
from src.cards import register


@register
class ChatCard(Card):
    """面向投资决策的 RAG 问答入口。"""

    name = "chat"
    endpoint = "/cards/chat"
    refresh = 0

    def get_data(self, **params) -> dict:
        return {
            "examples": [
                "TJ 最近怎么看 NVDA？",
                "过去 30 天哪些标的出现观点反转？",
                "dearbaibabybus 最近提到过哪些 AI 应用股？",
            ]
        }

    def _render_html(self, data: dict) -> str:
        examples = data.get("examples", [])
        chips = "".join(
            f'<button class="btn" data-action="fill-chat-question" data-question="{html.escape(str(q), quote=True)}" style="font-size:11px;padding:3px 8px">{html.escape(str(q))}</button>'
            for q in examples
        )
        return f'''<div class="card-title">问分析师库</div>
<div class="text-secondary mb-sm" style="font-size:11px;line-height:1.6">基于检索结果生成，仅供研究参考。若问题涉及实时价格，请先在数据管理中补全行情或查询行情源。</div>
<div class="flex mb-sm" style="gap:6px;align-items:flex-start">
  <textarea id="chat-question" placeholder="输入你想追问的标的、分析师或时间范围" style="flex:1;min-height:72px;font-size:12px;padding:8px;border-radius:8px;background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--border-primary)"></textarea>
  <button class="btn btn-primary" data-action="ask-chat" data-card="chat" style="font-size:12px;padding:8px 12px">提问</button>
</div>
<div class="mb-sm" style="display:flex;gap:4px;flex-wrap:wrap">{chips}</div>
<div id="chat-answer" class="text-secondary" style="font-size:12px;line-height:1.7">等待提问...</div>'''
