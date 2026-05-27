"""
准确率面板卡片（Accuracy）
===========================

展示各分析师的历史预测准确率指标：
30日胜率、平均收益、夏普比率。

数据来源: data/accuracy/*_accuracy.json 文件，
由 backtest_accuracy.py 脚本计算生成。
"""
import json
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class AccuracyCard(Card):
    """
    分析师准确率面板。

    展示各分析师的预测准确率指标，用于评估分析师信号的可信度。

    属性:
        name="accuracy"           — 唯一标识
        tab="dashboard"           — 属于主仪表盘标签页
        endpoint="/api/accuracy"  — API 路由
        refresh=300               — 每 5 分钟自动刷新
        template="accuracy.html"  — Jinja2 模板

    get_data() 数据来源:
        data/accuracy/{用户名}_accuracy.json 文件，
        每个文件包含 returns_30d 结构:
          - count: 有效预测次数
          - win_rate: 胜率（0~1）
          - avg_return: 平均收益
          - sharpe: 夏普比率

    返回结构:
        {
            "analysts": {
                "TJ_Research": {
                    "count": int,          # 30日有效预测数
                    "win_rate": int,       # 胜率百分比（已 ×100）
                    "avg_return": float,   # 平均收益百分比
                    "sharpe": float|null   # 夏普比率
                },
                ...
            }
        }
    """

    def get_data(self, **params) -> dict:
        result = {}
        for fp in Path("data/accuracy").glob("*_accuracy.json"):
            username = fp.stem.replace("_accuracy", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            r30 = d.get("returns_30d", {})
            result[username] = {
                "count": r30.get("count", 0),
                "win_rate": round(r30.get("win_rate", 0) * 100),
                "avg_return": round(r30.get("avg_return", 0) * 100, 1),
                "sharpe": r30.get("sharpe"),
            }
        return {"analysts": result}