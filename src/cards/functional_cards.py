"""流水线执行 + 资产代码 + 加密货币 + 脚本触发 + 情绪时间线 — 功能卡片"""
import json, csv, time, subprocess, sys
from pathlib import Path
from collections import Counter
from src.cards.base import Card
from src.cards import register
@register
class AssetAliasCard(Card):
    name = "asset_alias"
    tab = "pipeline"
    endpoint = "/api/asset_alias"
    refresh = 300

    def get_data(self, **params) -> dict:
        aliases = []
        fp = Path("data/stock_alias.csv")
        if fp.exists():
            reader = csv.DictReader(fp.read_text(encoding="utf-8").splitlines())
            for row in reader:
                aliases.append(dict(row))
        return {"aliases": aliases, "count": len(aliases),
                "known_crypto": ["BTC","ETH","XRP","SOL","DOGE","ADA","AVAX","DOT","MATIC"],
                "known_etf": ["SPY","QQQ","SOXX","SMH","ARKK","IWM","DIA","VOO","VTI","XLE","XLF","TQQQ","SQQQ","SOXL","SOXS"],
                "known_index": ["SPX","NDX","DJI","RUT","VIX"]}

    def _render_html(self, data: dict) -> str:
        count = data["count"]
        rows = "".join(
            f'<tr><td style="font-size:11px">{a.get("alias","")}</td><td style="font-weight:500">{a.get("ticker","")}</td><td>{a.get("type","")}</td></tr>'
            for a in data["aliases"][:20]
        )
        crypto_str = ", ".join(data.get("known_crypto", []))
        return f'''<div class="card-title">资产代码库</div>
<div class="grid grid-3 mb-sm">
  <div class="metric"><div class="metric-label">股票别名</div><div class="metric-value">{count}</div><div class="metric-sub">条映射</div></div>
  <div class="metric"><div class="metric-label">加密货币</div><div class="metric-value">{len(data.get("known_crypto",[]))}</div><div class="metric-sub">种</div></div>
  <div class="metric"><div class="metric-label">ETF+指数</div><div class="metric-value">{len(data.get("known_etf",[]))+len(data.get("known_index",[]))}</div><div class="metric-sub">只</div></div>
</div>
<div class="text-secondary mb-sm" style="font-size:11px">加密货币: {crypto_str}</div>
<table class="data"><tr><th>别名</th><th>Ticker</th><th>类型</th></tr>{rows}</table>
<div class="text-secondary mt-sm" style="font-size:11px">编辑: data/stock_alias.csv</div>'''


@register
class CryptoCard(Card):
    name = "crypto"
    tab = "insights"
    endpoint = "/api/crypto"
    refresh = 600

    def get_data(self, **params) -> dict:
        fp = Path("data/crypto_prices.json")
        prices = {}
        if fp.exists():
            prices = json.loads(fp.read_text(encoding="utf-8"))
        # 取最近价格
        latest = {}
        for ticker, data in prices.items():
            results = data.get("results", [])
            if results:
                latest[ticker] = {"price": results[-1].get("c", 0), "time": results[-1].get("t", 0)}
        return {"coins": latest, "total": len(prices)}

    def _render_html(self, data: dict) -> str:
        coins = data["coins"]
        if not coins:
            return '<div class="card-title">加密货币行情</div><div class="text-secondary">暂无数据，请运行流水线 fetch_crypto</div>'
        rows = "".join(
            f'<tr><td style="font-weight:500">{t}</td><td style="text-align:right">${c["price"]:.2f}</td><td style="text-align:right;font-size:11px">{time.strftime("%m-%d %H:%M", time.localtime(c["time"]/1000)) if c.get("time") else "?"}</td></tr>'
            for t, c in sorted(coins.items())
        )
        return f'<div class="card-title">加密货币行情</div><table class="data"><tr><th>币种</th><th style="text-align:right">价格 (USD)</th><th style="text-align:right">更新时间</th></tr>{rows}</table>'


@register
class ScriptRunnerCard(Card):
    name = "script_runner"
    tab = "pipeline"
    endpoint = "/api/script_runner"
    refresh = 0

    def get_data(self, **params) -> dict:
        scripts = {
            "信号量化": {"file": "compute_signals.py", "desc": "生成 0-100 分信号（需 analyzed_cleaned.json）", "group": "signal"},
            "共识联动": {"file": "compute_consensus.py", "desc": "多分析师信号共识分", "group": "signal"},
            "板块轮动": {"file": "compute_rotation.py", "desc": "周聚合 Z-score 热点", "group": "signal"},
            "准确率回溯": {"file": "backtest_accuracy.py", "desc": "30日胜率/夏普回溯", "group": "analysis"},
            "异常检测": {"file": "detect_anomaly.py", "desc": "KL 散度异常窗口", "group": "analysis"},
            "关联网络": {"file": "build_network.py", "desc": "投资者互动关系图", "group": "analysis"},
            "情绪时间线": {"file": "timeline_chart.py", "desc": "stance+价格双轴图表", "group": "viz"},
            "基本面快照": {"file": "fetch_fundamentals.py", "desc": "PE/ROE/营收增速", "group": "data"},
            "分析清洗": {"file": "clean_analysis.py", "desc": "股票/币种代码校准", "group": "data"},
        }
        return {"scripts": scripts}

    def _render_html(self, data: dict) -> str:
        groups = {}
        for name, info in data["scripts"].items():
            groups.setdefault(info["group"], []).append((name, info))
        html = '<div class="card-title">脚本工具箱</div>'
        for group, items in groups.items():
            btns = "".join(
                f'<button class="btn" onclick="runScript(\'{info["file"]}\')" style="margin:2px;font-size:11px" title="{info["desc"]}">{label}</button>'
                for label, info in items
            )
            html += f'<div class="mb-sm"><span class="text-secondary" style="font-size:11px">{group}</span><br>{btns}</div>'
        html += '<div id="sr_status" class="text-secondary mt-sm" style="font-size:11px"></div>'
        html += '''<script>
async function runScript(name){
  var s=document.getElementById("sr_status"); s.innerText="运行 scripts/"+name+"...";
  try{
    var r=await fetch("/cards/script_runner/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({script:name})});
    var d=await r.json(); s.innerText=d.ok?"完成: "+d.output:d.error;
    setTimeout(()=>location.reload(),1500);
  }catch(e){s.innerText="网络错误";}
}
</script>'''
        return html


@register
class TimelineCard(Card):
    name = "timeline"
    tab = "insights"
    endpoint = "/api/timeline"
    refresh = 600

    def get_data(self, **params) -> dict:
        charts = {}
        for fp in Path("data/timeline").glob("*.html"):
            name = fp.stem.replace("_timeline", "").replace("_", " ")
            charts[name] = str(fp)
        return {"charts": charts}

    def _render_html(self, data: dict) -> str:
        charts = data["charts"]
        if not charts:
            return '<div class="card-title">情绪时间线</div><div class="text-secondary">暂无图表。运行信号量化 + timeline_chart.py 生成。</div>'
        links = "".join(f'<div style="margin-bottom:4px"><a href="/timeline/{fp.stem}" target="_blank" style="font-size:12px">{name}</a></div>' for name, fp in charts.items())
        return f'<div class="card-title">情绪时间线</div>{links}<div class="text-secondary mt-sm" style="font-size:11px">点击在新窗口打开交互图表</div>'
