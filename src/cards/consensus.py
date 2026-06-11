"""
共识信号卡片（Consensus）
==========================

展示多分析师对同一股票/资产达成共识的排序结果。
共识分（consensus_score）越高，表示越多分析师在相近时间窗口内
对该标的同时发出同向信号，信号更可靠。

数据来源: data/consensus/*_consensus.json 文件，
由 compute_consensus.py 脚本计算生成。
"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class ConsensusCard(Card):
    """
    多分析师信号共识面板。

    展示共识分最高的 TOP 10 标的，以及多分析师参与（>=2人）的标的数。

    属性:
        name="consensus"           — 唯一标识
        tab="insights"             — 属于分析洞察标签页
        endpoint="/api/consensus"  — API 路由
        refresh=600                — 每 10 分钟自动刷新
        template="consensus.html"  — Jinja2 模板

    get_data() 数据来源:
        data/consensus/{ticker}_consensus.json 文件，
        每个文件存储该 ticker 在各时间窗口的共识计算结果，
        取最后一条（最新）数据。

    返回结构:
        {
            "top": [                         # TOP 10 共识标的（按 consensus_score 降序）
                {
                    "ticker": "NVDA",
                    "consensus_score": 85.5,
                    "analysts_in_window": ["TJ_Research", "xxx"],
                    ...
                },
                ...
            ],
            "total": int,                    # 有共识数据的总标的数
            "multi": int                     # 多分析师参与（>=2人）的标的数
        }
    """
    name = "consensus"
    def get_data(self, **params) -> dict:
        results = []
        for fp in Path("data/consensus").glob("*_consensus.json"):
            entries = json.loads(fp.read_text(encoding="utf-8"))
            if entries:
                e = {**entries[-1], "ticker": fp.stem.replace("_consensus", "")}
                results.append(e)
        results.sort(key=lambda x: x.get("consensus_score", 0), reverse=True)
        multi = sum(1 for r in results if len(r.get("analysts_in_window", [])) >= 2)
        return {"top": results[:10], "total": len(results), "multi": multi}
