"""流水线执行 + 资产代码 + 加密货币 + 脚本触发 + 情绪时间线 — 功能卡片"""
import json, csv, time
from pathlib import Path
from collections import Counter
from src.cards.base import Card
from src.cards import register


def _esc_js(s: str) -> str:
    """转义字符串用于 JS onclick 属性中，防注入。"""
    return json.dumps(str(s))[1:-1].replace("'", "\\'")


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
            reader = csv.reader(fp.read_text(encoding="utf-8").splitlines())
            for row in reader:
                if not row or not row[0] or row[0].startswith("#"):
                    continue
                alias = row[0].strip() if len(row) >= 1 else ""
                ticker = row[1].strip() if len(row) >= 2 else ""
                notes = row[2].strip() if len(row) >= 3 else ""
                if alias:
                    aliases.append({"alias": alias, "ticker": ticker, "type": notes})
        # 拆分：已确认(ticker非空) vs 待判断(ticker为空且notes非SKIP) vs 已跳过(notes=SKIP)
        confirmed = [a for a in aliases if a["ticker"]]
        pending = [a for a in aliases if not a["ticker"] and a.get("type") != "SKIP"]
        skipped = [a for a in aliases if not a["ticker"] and a.get("type") == "SKIP"]
        return {"aliases": aliases, "count": len(aliases),
                "confirmed": confirmed, "pending": pending, "skipped": skipped,
                "n_confirmed": len(confirmed), "n_pending": len(pending), "n_skipped": len(skipped),
                "known_crypto": ["BTC","ETH","XRP","SOL","DOGE","ADA","AVAX","DOT","MATIC"],
                "known_etf": ["SPY","QQQ","SOXX","SMH","ARKK","IWM","DIA","VOO","VTI","XLE","XLF","TQQQ","SQQQ","SOXL","SOXS"],
                "known_index": ["SPX","NDX","DJI","RUT","VIX"]}

    def _render_html(self, data: dict) -> str:
        count = data["count"]
        confirmed = data["confirmed"]
        pending = data["pending"]

        # ── 已确认映射行 ──
        confirmed_rows = ""
        if confirmed:
            confirmed_rows = "".join(
                f'''<tr>
  <td style="font-size:11px">{a["alias"]}</td>
  <td style="font-weight:500">{a["ticker"]}</td>
  <td style="font-size:11px;color:var(--text-secondary)">{a.get("type","")}</td>
  <td style="text-align:right">
    <button class="btn" style="font-size:10px;padding:1px 6px" onclick="editAliasRow('{_esc_js(a["alias"])}','{_esc_js(a["ticker"])}','{_esc_js(a.get("type",""))}')">编辑</button>
    <button class="btn btn-danger" style="font-size:10px;padding:1px 6px" onclick="deleteAlias('{_esc_js(a["alias"])}')">删除</button>
  </td></tr>'''
                for a in confirmed[:50]
            )
        else:
            confirmed_rows = '<tr><td colspan="4" class="text-secondary">暂无已确认映射</td></tr>'

        # ── 待人工判断行 ──
        pending_rows = ""
        if pending:
            pending_rows = "".join(
                f'''<tr style="background:rgba(239,159,39,0.05)">
  <td style="font-size:11px;font-weight:500">{a["alias"]}</td>
  <td style="font-size:11px;color:var(--text-secondary)">{a.get("type","")}</td>
  <td style="text-align:right">
    <button class="btn" style="font-size:10px;padding:1px 6px" onclick="fillAliasForm('{_esc_js(a["alias"])}','{_esc_js(a.get("type",""))}')">填代码</button>
    <button class="btn" style="font-size:10px;padding:1px 6px;border-color:var(--text-tertiary);color:var(--text-tertiary)" onclick="skipAlias('{_esc_js(a["alias"])}')">跳过</button>
    <button class="btn btn-danger" style="font-size:10px;padding:1px 6px" onclick="deleteAlias('{_esc_js(a["alias"])}')">删除</button>
  </td></tr>'''
                for a in pending[:30]
            )
        else:
            pending_rows = '<tr><td colspan="4" class="text-secondary" style="color:var(--text-success)">🎉 全部确认完毕</td></tr>'

        # ── 已跳过行 ──
        skipped = data.get("skipped", [])
        skipped_rows = ""
        if skipped:
            skipped_rows = "".join(
                f'''<tr style="opacity:0.5">
  <td style="font-size:11px">{a["alias"]}</td>
  <td style="font-size:11px;color:var(--text-secondary)">{a.get("type","")}</td>
  <td style="text-align:right">
    <button class="btn" style="font-size:10px;padding:1px 6px" onclick="unskipAlias('{_esc_js(a["alias"])}')">恢复</button>
  </td></tr>'''
                for a in skipped[:30]
            )

        crypto_str = ", ".join(data.get("known_crypto", []))
        return f'''<div class="card-title">资产代码库</div>
<div class="grid grid-4 mb-sm">
  <div class="metric"><div class="metric-label">总映射</div><div class="metric-value">{count}</div><div class="metric-sub">条</div></div>
  <div class="metric"><div class="metric-label">已确认</div><div class="metric-value" style="color:var(--text-success)">{data["n_confirmed"]}</div><div class="metric-sub">ticker 明确</div></div>
  <div class="metric"><div class="metric-label">待判断</div><div class="metric-value" style="color:var(--text-warning)">{data["n_pending"]}</div><div class="metric-sub">需人工</div></div>
  <div class="metric"><div class="metric-label">已跳过</div><div class="metric-value" style="color:var(--text-tertiary)">{data["n_skipped"]}</div><div class="metric-sub">暂不处理</div></div>
</div>

<!-- 添加 / 编辑表单 -->
<div class="flex mb-sm" style="gap:4px;flex-wrap:wrap">
  <input id="aa_alias" placeholder="别名" style="flex:1;min-width:80px;font-size:11px;padding:4px 6px" />
  <input id="aa_ticker" placeholder="代码" style="flex:1;min-width:60px;font-size:11px;padding:4px 6px" />
  <input id="aa_notes" placeholder="备注" style="flex:1;min-width:60px;font-size:11px;padding:4px 6px" />
  <button class="btn btn-primary" onclick="addAlias()" style="font-size:11px;padding:4px 10px" id="btn_aa_submit">添加</button>
</div>
<input type="hidden" id="aa_old_alias" value="" />
<span id="aa_status" class="text-secondary" style="font-size:10px"></span>

<!-- 已确认映射 -->
<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500">已确认映射 ({data["n_confirmed"]}条)</span></div>
<table class="data" style="margin-bottom:0"><tr><th>别名</th><th>Ticker</th><th>备注</th><th style="text-align:right">操作</th></tr>{confirmed_rows}</table>

<!-- 待人工判断 -->
<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-warning)">⚠ 待人工判断 ({data["n_pending"]}条)</span></div>
<table class="data"><tr><th>别名</th><th>系统标注</th><th style="text-align:right">操作</th></tr>{pending_rows}</table>
<!-- 已跳过 -->
{skipped_rows and f'<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-tertiary)">⊘ 已跳过 ({data["n_skipped"]}条)</span></div><table class="data"><tr><th>别名</th><th>系统标注</th><th style="text-align:right">操作</th></tr>' + skipped_rows + '</table>'}
<div class="text-secondary mt-sm" style="font-size:10px">提示：点"填代码"自动回填表单，输入 ticker 后提交即可移入已确认列表。跳过则暂不处理。内置识别: {crypto_str}</div>'''


@register
class CryptoCard(Card):
    name = "crypto"
    tab = "insights"
    endpoint = "/api/crypto"
    refresh = 300
    template = "crypto.html"

    def get_data(self, **params) -> dict:
        import re as _re
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

        # 查询推文提及次数（信号强度代理指标）
        mentions = {}
        coins = list(latest.keys()) or ["BTC", "ETH", "XRP", "SOL", "DOGE"]
        try:
            import sqlite3
            conn = sqlite3.connect("data/twitter_data.db")
            for coin in coins:
                pattern = f"%${coin}%"
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM tweets WHERE text LIKE ?", (pattern,)
                ).fetchone()[0]
                if cnt > 0:
                    mentions[coin] = cnt
        except Exception:
            pass
        finally:
            try: conn.close()
            except: pass

        return {"coins": latest, "mentions": mentions, "total_coins": len(latest)}

    def _render_html(self, data: dict) -> str:
        import time as _time_module
        coins = data["coins"]
        mentions = data.get("mentions", {})
        if not coins:
            return '<div class="card-title">加密货币信号</div><div class="text-secondary">暂无价格数据。运行流水线 fetch_crypto 获取。</div>'

        # 按提及次数排序，再按市值排序
        def sort_key(item):
            t, c = item
            return (-mentions.get(t, 0), -c.get("price", 0))
        sorted_coins = sorted(coins.items(), key=sort_key)

        rows = ""
        for t, c in sorted_coins:
            price = c["price"]
            ts = c.get("time", 0)
            time_str = _time_module.strftime("%m-%d %H:%M", _time_module.localtime(ts/1000)) if ts else "?"
            mcnt = mentions.get(t, 0)
            signal = ""
            if mcnt >= 5:
                signal = '<span class="tag tag-warn">🔥 热议</span>'
            elif mcnt >= 2:
                signal = '<span class="tag tag-ok">提及 {0}次</span>'.format(mcnt)
            elif mcnt == 1:
                signal = '<span style="font-size:10px;color:var(--text-tertiary)">{0}次</span>'.format(mcnt)
            else:
                signal = '<span style="font-size:10px;color:var(--text-tertiary)">-</span>'

            rows += f'<tr><td style="font-weight:500">{t}</td><td style="text-align:right">${price:.2f}</td><td style="text-align:center">{signal}</td><td style="text-align:right;font-size:11px;color:var(--text-tertiary)">{time_str}</td></tr>'

        total_mentions = sum(mentions.values())
        return f'''<div class="card-title">加密货币信号</div>
<div class="mb-sm"><span class="text-secondary" style="font-size:11px">覆盖 {data["total_coins"]} 种 · 分析师提及 {total_mentions} 次</span></div>
<table class="data"><tr><th>币种</th><th style="text-align:right">价格 (USD)</th><th style="text-align:center">推文信号</th><th style="text-align:right">更新</th></tr>{rows}</table>
<div class="text-secondary mt-sm" style="font-size:11px">信号基于推文中 $TICKER 提及次数。在"角色代入"选币时可参考。</div>'''


@register
class ScriptRunnerCard(Card):
    name = "script_runner"
    tab = "pipeline"
    endpoint = "/api/script_runner"
    refresh = 0
    template = "script_runner.html"

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
        # 转换为模板需要的 groups 格式
        groups = {}
        for name, info in scripts.items():
            groups.setdefault(info["group"], []).append((name, info))
        return {"groups": groups}


@register
class TimelineCard(Card):
    name = "timeline"
    tab = "insights"
    endpoint = "/api/timeline"
    refresh = 600
    template = "timeline.html"

    def get_data(self, **params) -> dict:
        charts = {}
        for fp in Path("data/timeline").glob("*.html"):
            name = fp.stem.replace("_timeline", "").replace("_", " ")
            charts[name] = fp.stem
        return {"charts": charts}
