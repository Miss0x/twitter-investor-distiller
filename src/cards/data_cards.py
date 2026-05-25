"""共识 / 轮动 / 异常 / 网络 / 系统状态 — 渲染卡片"""
import json
from pathlib import Path
from collections import defaultdict
from src.cards.base import Card
from src.cards import register


@register
class ConsensusCard(Card):
    name = "consensus"; tab = "insights"; endpoint = "/api/consensus"; refresh = 600

    def get_data(self, **params) -> dict:
        results = []
        for fp in Path("data/consensus").glob("*_consensus.json"):
            entries = json.loads(fp.read_text(encoding="utf-8"))
            if entries:
                e = entries[-1]; e["ticker"] = fp.stem.replace("_consensus", "")
                results.append(e)
        results.sort(key=lambda x: x.get("consensus_score", 0), reverse=True)
        multi = sum(1 for r in results if len(r.get("analysts_in_window", [])) >= 2)
        return {"top": results[:10], "total": len(results), "multi": multi}

    def _render_html(self, data: dict) -> str:
        rows = "".join(f'<tr><td style="font-weight:500">{r["ticker"]}</td><td style="text-align:right;font-weight:500;color:var(--text-success)">{r["consensus_score"]:.0f}</td><td style="text-align:right;font-size:11px">{"🔥" if len(r.get("analysts_in_window",[]))>=2 else ""} {r.get("signal_count",0)}条</td></tr>' for r in data["top"][:5])
        return f'<div class="card-title">共识 TOP 5</div><table class="data"><tr><th>股票</th><th style="text-align:right">得分</th><th style="text-align:right">信号</th></tr>{rows}</table><div class="text-secondary mt-sm">{data["total"]}只覆盖, {data["multi"]}只双人</div>'


@register
class RotationCard(Card):
    name = "rotation"; tab = "insights"; endpoint = "/api/rotation"; refresh = 600

    def get_data(self, **params) -> dict:
        results = {}
        for fp in Path("data/rotation").glob("*_rotation.json"):
            username = fp.stem.replace("_rotation", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            weeks = sorted({r["week"] for r in d})
            if weeks:
                hot = sorted([r for r in d if r["week"] == weeks[-1]], key=lambda x: x["z_score"], reverse=True)[:5]
                results[username] = [{"topic": r["topic"], "z": r["z_score"], "count": r["count"]} for r in hot]
        return {"rotation": results}

    def _render_html(self, data: dict) -> str:
        items = []
        for u, topics in data["rotation"].items():
            for t in topics:
                items.append(f'<div class="flex-between" style="font-size:12px;margin-bottom:4px"><span>{u} · {t["topic"]}</span><span style="font-weight:500;color:var(--text-success)">{t["z"]:+.1f}σ</span></div>')
        return f'<div class="card-title">板块轮动热点</div>{"".join(items[:8])}'


@register
class NetworkCard(Card):
    name = "network"; tab = "insights"; endpoint = "/api/network"; refresh = 3600

    def get_data(self, **params) -> dict:
        fp = Path("data/network/investor_network.json")
        if not fp.exists(): return {"recs": []}
        d = json.loads(fp.read_text(encoding="utf-8"))
        return {"recs": d.get("recommendations", [])[:5], "edges": len(d.get("edges", [])), "nodes": len(d.get("nodes", []))}

    def _render_html(self, data: dict) -> str:
        rows = "".join(f'<div class="flex-between" style="font-size:12px;margin-bottom:4px"><span style="font-weight:500">{r["user"]}</span><span class="text-secondary">被引 {r["in_degree"]}次</span></div>' for r in data["recs"])
        return f'<div class="card-title">信源推荐</div>{rows}<div class="text-secondary mt-sm">{data["nodes"]}节点, {data["edges"]}边</div>'


@register
class SystemStatusCard(Card):
    name = "system_status"; tab = "dashboard"; endpoint = "/api/system_status"; refresh = 60

    def get_data(self, **params) -> dict:
        from src.storage.database import db
        from src.storage.models import Tweet
        db.init_db(); s = db.get_session()
        tweets = s.query(Tweet).count(); s.close()
        pipeline = len(list(Path("data/pipeline").glob("*_analyzed_cleaned.json")))
        portraits = len(list(Path("data/pipeline").glob("*portrait.md")))
        signals = 0
        for fp in Path("data/pipeline").glob("*_analyzed_cleaned.json"):
            for r in json.loads(fp.read_text(encoding="utf-8")):
                if r.get("signal_score"): signals += 1
        return {"tweets": tweets, "analyzed": pipeline, "portraits": portraits, "signals": signals}

    def _render_html(self, data: dict) -> str:
        items = [("数据库", f'{data["tweets"]}条'), ("画像", f'{data["portraits"]}份'), ("信号", f'{data["signals"]}条'), ("分析文件", f'{data["analyzed"]}个')]
        rows = "".join(f'<div class="flex-between" style="font-size:12px;margin-bottom:4px"><span class="text-secondary">{k}</span><span>{v}</span></div>' for k, v in items)
        return f'<div class="card-title">系统状态</div>{rows}'


@register
class AnomalyCard(Card):
    name = "anomaly"; tab = "insights"; endpoint = "/api/anomaly"; refresh = 600

    def get_data(self, **params) -> dict:
        results = {}
        for fp in Path("data/anomaly").glob("*_anomaly.json"):
            tag = fp.stem.replace("_anomaly", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            anoms = [r for r in d if r["anomaly"]]
            if anoms:
                results[tag] = {"count": len(anoms), "total": len(d), "recent": [{"kl": a["kl_avg"], "topics": a["topics"][:3]} for a in anoms[-3:]]}
        return {"anomalies": results}

    def _render_html(self, data: dict) -> str:
        items = []
        for tag, info in data["anomalies"].items():
            kls = " / ".join(f'{a["kl"]:.2f}' for a in info["recent"][:3])
            items.append(f'<div class="flex-between" style="font-size:12px;margin-bottom:6px"><span class="text-secondary">{tag}</span><span style="color:var(--text-warning);font-size:11px">KL {kls}</span></div>')
        return f'<div class="card-title">异常检测</div>{"".join(items[:6]) or "<div class=\"text-secondary\">无异常</div>"}'
