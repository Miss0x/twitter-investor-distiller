"""
异常检测卡片（Anomaly）
========================

检测分析师言论风格的异常窗口。
通过 KL 散度（Kullback-Leibler Divergence）衡量
当前窗口的话题分布与历史均值的偏离程度。
KL 值越大，表示该时间窗口的分析师话题分布越不正常。

数据来源: data/anomaly/*_anomaly.json 文件，
由 detect_anomaly.py 脚本计算生成。
"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class AnomalyCard(Card):
    """
    KL 散度异常检测面板。

    展示各分析师/分析维度中检测到异常的时间窗口。
    anomaly=True 表示该窗口的话题分布显著偏离历史模式。

    属性:
        name="anomaly"             — 唯一标识
        tab="insights"             — 属于分析洞察标签页
        endpoint="/api/anomaly"    — API 路由
        refresh=600                — 每 10 分钟自动刷新
        template="anomaly.html"    — Jinja2 模板

    get_data() 数据来源:
        data/anomaly/*_anomaly.json 文件，
        筛选 anomaly=True 的窗口，取最近 3 条。

    返回结构:
        {
            "anomalies": {
                "TJ_Research": {
                    "count": 5,      # 异常窗口总数
                    "total": 20,     # 检查的总窗口数
                    "recent": [      # 最近 3 条异常窗口
                        {
                            "kl": 0.45,              # KL 散度均值
                            "topics": ["topic1", ...] # 主要偏离话题
                        },
                        ...
                    ]
                },
                ...
            }
        }
    """
    name = "anomaly"
    def get_data(self, **params) -> dict:
        results = {}
        for fp in Path("data/anomaly").glob("*_anomaly.json"):
            tag = fp.stem.replace("_anomaly", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            anoms = [r for r in d if r["anomaly"]]
            if anoms:
                results[tag] = {"count": len(anoms), "total": len(d),
                                "recent": [{"kl": a["kl_avg"], "topics": a["topics"][:3]} for a in anoms[-3:]]}
        return {"anomalies": results}