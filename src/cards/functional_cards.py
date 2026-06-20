"""
功能卡片组（Functional Cards）
================================

包含四个数据管理/信号展示卡片：
  1. AssetAliasCard    — 资产别名映射管理（股票/代码关联表格）
  2. CryptoCard        — 加密货币价格 + 推文提及信号
  3. ScriptRunnerCard  — 后台分析脚本触发器（信号/清洗/网络等）
  4. TimelineCard      — 情绪时间线图表浏览
"""
import json
import html
from pathlib import Path
from src.cards.base import Card
from src.cards import register


# ────────────────────────────────────────────────────────────
# 工具函数
# ────────────────────────────────────────────────────────────

def _attr(s: str) -> str:
    """
    HTML 属性值安全转义函数。

    转义 & < > " 四个字符用于嵌入 HTML 属性值内部（如 data-* 属性），
    防止属性值注入攻击。基于标准库 html.escape(quote=True)。
    """
    return html.escape(str(s), quote=True)


@register
class AssetAliasCard(Card):
    """
    资产别名映射管理卡片。

    管理分析师推文中提到的"资产别名"与标准 ticker 代码的映射关系。
    例如："纳指" → NQ（纳斯达克指数），"苹果" → AAPL。

    别名有三种状态:
      - 已确认(confirmed): ticker 已填写，映射明确
      - 待判断(pending): ticker 为空且未被跳过，需人工确认
      - 已跳过(skipped): 标注为 SKIP|xxx，表示该别名不需要映射

    属性:
        name="asset_alias"       — 唯一标识
        tab="pipeline"           — 属于流水线标签页
        endpoint="/api/asset_alias" — API 路由
        refresh=300              — 每 5 分钟自动刷新
    """
    name = "asset_alias"
    tab = "pipeline"
    endpoint = "/api/asset_alias"
    refresh = 300

    def get_data(self, **params) -> dict:
        """
        从 data/stock_alias.csv 读取别名映射数据。

        CSV 格式: alias, ticker, notes （不含表头，# 开头的行视为注释）
        数据按 ticker 是否为空和 notes 是否以 SKIP 开头分为三类。

        返回结构:
            {
                "aliases": [{alias, ticker, type}, ...],  # 全部别名
                "count": int,                                # 总条数
                "confirmed": [...],                          # 已确认列表
                "pending": [...],                            # 待判断列表
                "skipped": [...],                            # 已跳过列表
                "n_confirmed": int, "n_pending": int, "n_skipped": int,
                "known_crypto": ["BTC","ETH",...],           # 已知加密货币列表
                "known_etf": ["SPY","QQQ",...],              # 已知 ETF 列表
                "known_index": ["SPX","NDX",...]             # 已知指数列表
            }
        """
        aliases = []
        try:
            from src.storage.alias_repository import AliasRepository
            raw = AliasRepository.get_all()
            # NamedTuple → dict（模板使用 dict 访问语法）
            aliases = [{"alias": a.alias, "ticker": a.ticker, "type": a.notes} for a in raw]
        except Exception:
            pass
        # 拆分：已确认(ticker非空) vs 待判断(ticker为空且notes非SKIP) vs 已跳过(notes=SKIP)
        confirmed = [a for a in aliases if a["ticker"]]
        pending = [a for a in aliases if not a["ticker"] and not a.get("type","").startswith("SKIP")]
        skipped = [a for a in aliases if not a["ticker"] and a.get("type","").startswith("SKIP")]
        return {"aliases": aliases, "count": len(aliases),
                "confirmed": confirmed, "pending": pending, "skipped": skipped,
                "n_confirmed": len(confirmed), "n_pending": len(pending), "n_skipped": len(skipped),
                "known_crypto": ["BTC","ETH","XRP","SOL","DOGE","ADA","AVAX","DOT","MATIC"],
                "known_etf": ["SPY","QQQ","SOXX","SMH","ARKK","IWM","DIA","VOO","VTI","XLE","XLF","TQQQ","SQQQ","SOXL","SOXS"],
                "known_index": ["SPX","NDX","DJI","RUT","VIX"]}

    def _render_html(self, data: dict) -> str:
        """
        生成标的代码映射管理界面的 HTML。

        HTML 结构概览:
            1. 四格统计面板 — 总映射/已确认/待判断/已跳过
            2. 添加/编辑表单 — 提及名称 + 标的代码 + 备注 输入框
            3. 已确认映射表格 — 提及名称 | 标的代码 | 备注 | 操作(编辑/删除)
            4. 待人工判断表格 — 提及名称 | 系统标注 | 操作(填写代码/跳过/删除)
            5. 已跳过表格（可折叠）— 提及名称 | 系统标注 | 操作(恢复)
            6. 底部提示 — 内置识别列表
        """
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
    <button class="btn" style="font-size:10px;padding:1px 6px" data-action="edit-alias" data-alias="{_attr(a["alias"])}" data-ticker="{_attr(a["ticker"])}" data-notes="{_attr(a.get("type",""))}">编辑</button>
    <button class="btn btn-danger" style="font-size:10px;padding:1px 6px" data-action="delete-alias" data-alias="{_attr(a["alias"])}">删除</button>
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
    <button class="btn" style="font-size:10px;padding:1px 6px" data-action="fill-alias" data-alias="{_attr(a["alias"])}" data-notes="{_attr(a.get("type",""))}">填写代码</button>
    <button class="btn" style="font-size:10px;padding:1px 6px;border-color:var(--text-tertiary);color:var(--text-tertiary)" data-action="skip-alias" data-alias="{_attr(a["alias"])}">跳过</button>
    <button class="btn btn-danger" style="font-size:10px;padding:1px 6px" data-action="delete-alias" data-alias="{_attr(a["alias"])}">删除</button>
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
  <td style="font-size:11px;color:var(--text-secondary)">{a.get("type","").replace("SKIP|","",1) if a.get("type","").startswith("SKIP|") else a.get("type","")}</td>
  <td style="text-align:right">
    <button class="btn" style="font-size:10px;padding:1px 6px" data-action="unskip-alias" data-alias="{_attr(a["alias"])}">恢复</button>
  </td></tr>'''
                for a in skipped[:30]
            )

        crypto_str = ", ".join(data.get("known_crypto", []))
        return f'''<div class="card-title">标的代码映射</div>
<div class="grid grid-4 mb-sm">
  <div class="metric"><div class="metric-label">总映射</div><div class="metric-value">{count}</div><div class="metric-sub">条</div></div>
  <div class="metric"><div class="metric-label">已确认</div><div class="metric-value" style="color:var(--text-success)">{data["n_confirmed"]}</div><div class="metric-sub">代码明确</div></div>
  <div class="metric"><div class="metric-label">待判断</div><div class="metric-value" style="color:var(--text-warning)">{data["n_pending"]}</div><div class="metric-sub">需人工</div></div>
  <div class="metric"><div class="metric-label">已跳过</div><div class="metric-value" style="color:var(--text-tertiary)">{data["n_skipped"]}</div><div class="metric-sub">暂不处理</div></div>
</div>

<!-- 添加 / 编辑表单 -->
<div class="flex mb-sm" style="gap:4px;flex-wrap:wrap" data-card-context="asset_alias">
  <input id="asset_alias-aa_alias" placeholder="提及名称" style="flex:1;min-width:80px;font-size:11px;padding:4px 6px" />
  <input id="asset_alias-aa_ticker" placeholder="标的代码" style="flex:1;min-width:60px;font-size:11px;padding:4px 6px" />
  <input id="asset_alias-aa_notes" placeholder="备注" style="flex:1;min-width:60px;font-size:11px;padding:4px 6px" />
  <button class="btn btn-primary" data-action="add-alias" data-card="asset_alias" style="font-size:11px;padding:4px 10px" id="asset_alias-btn_aa_submit">添加</button>
</div>
<input type="hidden" id="asset_alias-aa_old_alias" value="" />
<span id="asset_alias-aa_status" class="text-secondary" style="font-size:10px"></span>

<!-- 已确认映射 -->
<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500">已确认映射 ({data["n_confirmed"]}条)</span></div>
<table class="data" style="margin-bottom:0"><tr><th>提及名称</th><th>标的代码</th><th>备注</th><th style="text-align:right">操作</th></tr>{confirmed_rows}</table>

<!-- 待人工判断 -->
<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-warning)">⚠ 待人工判断 ({data["n_pending"]}条)</span></div>
<table class="data"><tr><th>提及名称</th><th>系统标注</th><th style="text-align:right">操作</th></tr>{pending_rows}</table>
<!-- 已跳过 -->
{skipped_rows and f'<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-tertiary)">⊘ 已跳过 ({data["n_skipped"]}条)</span></div><table class="data"><tr><th>提及名称</th><th>系统标注</th><th style="text-align:right">操作</th></tr>' + skipped_rows + '</table>'}
<div class="text-secondary mt-sm" style="font-size:10px">提示：点"填写代码"自动回填表单，输入标的代码后提交即可移入已确认列表。跳过则暂不处理。内置识别: {crypto_str}</div>'''


@register
class CryptoCard(Card):
    """
    加密货币信号卡片。

    展示已抓取的加密货币价格 + 分析师推文中 $TICKER 的提及频率（信号强度代理指标）。

    属性:
        name="crypto"            — 唯一标识
        tab="insights"           — 属于分析洞察标签页
        endpoint="/api/crypto"   — API 路由
        refresh=300              — 每 5 分钟自动刷新
        template=None            — 使用 _render_html() 渲染（包含提及信号列）
    """
    name = "crypto"
    tab = "insights"
    endpoint = "/api/crypto"
    refresh = 300
    # template removed — uses _render_html() which includes mentions/signal column (规则二)

    def get_data(self, **params) -> dict:
        """
        从 data/crypto_prices.json 和 twitter_data.db 获取数据。

        数据来源:
            - data/crypto_prices.json: Polygon.io 或类似 API 抓取的币价历史
            - twitter_data.db tweets 表: 搜索 $BTC, $ETH 等模式匹配统计提及次数

        返回结构:
            {
                "coins": {               # 各币种最新价格
                    "BTC": {"price": float, "time": int},
                    "ETH": {...},
                    ...
                },
                "mentions": {            # 各币种在推文中的提及次数
                    "BTC": int,
                    "ETH": int,
                    ...
                },
                "total_coins": int       # 有价格数据的币种总数
            }
        """
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

        # 查询推文提及次数（ORM 循环，数据量小时等价于单 SQL）
        mentions = {}
        coins = list(latest.keys()) or ["BTC", "ETH", "XRP", "SOL", "DOGE"]
        try:
            from src.storage.database import db
            from src.storage.models import Tweet
            s = db.get_session()
            try:
                for coin in coins:
                    cnt = s.query(Tweet).filter(Tweet.text.like(f"%${coin}%")).count()
                    if cnt > 0:
                        mentions[coin] = cnt
            finally:
                s.close()
        except Exception:
            pass

        return {"coins": latest, "mentions": mentions, "total_coins": len(latest)}

    def _render_html(self, data: dict) -> str:
        """
        生成加密货币信号表格的 HTML（模板不存在时的 fallback）。

        HTML 结构概览:
            1. 标题栏 — "加密货币信号"
            2. 概览行 — 覆盖币种数 + 分析师提及总次数
            3. 数据表格 — 币种 | 价格(USD) | 推文信号(热议/提及N次/-) | 更新时间
               按提及次数降序排列，价格作为次级排序键
            4. 底部说明 — 信号来源说明
        """
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
    """
    脚本运行器卡片。

    提供一键触发后台分析脚本的界面。
    每个脚本按 group 分组展示（signal/analysis/viz/data），
    通过模板渲染带参数字段的表单。

    属性:
        name="script_runner"       — 唯一标识
        tab="pipeline"             — 属于流水线标签页
        endpoint="/api/script_runner" — API 路由
        refresh=0                  — 不自动刷新（手动触发）
        template="script_runner.html" — Jinja2 模板

    脚本列表（scripts dict）:
        - 信号量化: compute_signals.py      → 生成 0-100 分信号评分
        - 共识联动: compute_consensus.py    → 多分析师信号共识
        - 板块轮动: compute_rotation.py     → 周聚合 Z-score 热点
        - 准确率回溯: backtest_accuracy.py  → 30日胜率/夏普比率
        - 异常检测: detect_anomaly.py       → KL 散度异常检测
        - 关联网络: build_network.py        → 投资者互动关系图
        - 情绪时间线: timeline_chart.py     → stance+价格双轴图表
        - 基本面快照: fetch_fundamentals.py → PE/ROE/营收增速
        - 分析清洗: clean_analysis.py       → 股票/币种代码校准
    """
    name = "script_runner"
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
    """
    情绪时间线卡片。

    浏览 data/timeline/ 目录下的情绪时间线 HTML 图表文件。
    每张图表展示某位分析师对某资产的情绪 stance 变化与价格走势的双轴对比。

    属性:
        name="timeline"           — 唯一标识
        tab="insights"            — 属于分析洞察标签页
        endpoint="/api/timeline"  — API 路由
        refresh=600               — 每 10 分钟自动刷新
        template="timeline.html"  — Jinja2 模板

    get_data() 返回结构:
        {
            "charts": {
                "显示名": "文件名前缀",  # 用于构建 iframe src
                ...
            }
        }
    """
    name = "timeline"
    def get_data(self, **params) -> dict:
        charts = {}
        for fp in Path("data/timeline").glob("*.html"):
            name = fp.stem.replace("_timeline", "").replace("_", " ")
            charts[name] = fp.stem
        return {"charts": charts}
