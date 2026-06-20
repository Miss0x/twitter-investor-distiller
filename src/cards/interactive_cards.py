"""
交互卡片组（Interactive Cards）
================================

包含四个交互功能卡片：
  1. DaemonCard     — 守护进程状态面板（自动拉取推文的后台服务）
  2. TelegramCard   — Telegram 通知配置面板（bot token + chat ID）
  3. RolePickerCard — 角色代入选股面板（选择分析师并生成投资方案）
  4. PortfolioCard  — 持股顾问面板（输入持仓获取建议）
"""
import json
import time
from pathlib import Path
from collections import defaultdict
from src.cards.base import Card
from src.cards import register


@register
class DaemonCard(Card):
    """
    守护进程状态卡片。

    监控自动拉取推文的后台守护进程状态，展示当日采样进度。

    属性:
        name="daemon"            — 唯一标识
        tab="dashboard"          — 属于主仪表盘标签页
        endpoint="/api/daemon"   — API 路由
        refresh=5                — 每 5 秒自动刷新（状态变化快）
        template="daemon.html"   — Jinja2 模板
    """
    name = "daemon"

    def get_data(self, **params) -> dict:
        """
        从 auto_scheduler_state.json 和 DB 获取守护进程状态。

        数据来源:
            - data/auto_scheduler_state.json: running 标志、last_id 游标
            - PipelineTask 表: 当日 analyze 任务计数

        返回结构:
            {
                "running": bool,   # 守护进程是否正在运行
                "last_id": int,    # 最后处理的推文 ID
                "today": int,      # 当日已抽样推文数（analyze 任务数）
                "budget": int      # 当日预算上限（目前固定 20）
            }
        """
        state = Path("data/auto_scheduler_state.json")
        raw = json.loads(state.read_text()) if state.exists() else {}
        running = raw.get("running", False)
        last_id = raw.get("last_id", 0)
        try:
            from src.storage.database import db
            from src.storage.models import PipelineTask
            db.init_db()
            s = db.get_session()
            try:
                cnt = s.query(PipelineTask).filter(PipelineTask.task_type == "analyze", PipelineTask.created_at >= time.strftime("%Y-%m-%d")).count()
            finally:
                s.close()
        except Exception:
            cnt = 0
        return {"running": running, "last_id": last_id, "today": cnt, "budget": 20}


@register
class TelegramCard(Card):
    """
    Telegram 通知配置卡片。

    管理 Telegram Bot 连接配置，用于推送分析结果通知。

    属性:
        name="telegram"           — 唯一标识
        tab="dashboard"           — 属于主仪表盘标签页
        endpoint="/api/telegram"  — API 路由
        template="telegram.html"  — Jinja2 模板

    get_data() 返回结构:
        {
            "configured": bool,       # Bot Token 是否已配置
            "chat_id": str,           # 目标聊天 ID
            "token_preview": str      # Bot Token 预览（前12字符+...）
        }
    """
    name = "telegram"

    def get_data(self, **params) -> dict:
        fp = Path("data/telegram_config.json")
        cfg = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
        return {"configured": bool(cfg.get("bot_token")), "chat_id": cfg.get("chat_id", ""),
                "token_preview": (cfg.get("bot_token", "")[:12] + "...") if cfg.get("bot_token") else ""}

    # _render_html removed — template telegram.html handles rendering (规则二)


@register
class RolePickerCard(Card):
    """
    角色代入选股卡片。

    选择一个分析师，AI 会以该分析师的风格和偏好生成投资组合方案。
    分析师的分析结果文件（*_analyzed_cleaned.json）提供其关注股票池。

    属性:
        name="role_picker"        — 唯一标识
        tab="insights"            — 属于分析洞察标签页
        endpoint="/api/role_picker" — API 路由
        refresh=0（默认）          — 不自动刷新

    get_data() 返回结构:
        {
            "analysts": ["TJ_Research", ...],   # 可用分析师列表
            "sectors": {                         # 行业板块 → 股票列表
                "Technology / Semiconductors": ["NVDA", "AMD", ...],
                ...
            }
        }
    """
    name = "role_picker"
    def get_data(self, **params) -> dict:
        analysts = set()
        for fp in Path("data/pipeline").glob("*_analyzed_cleaned.json"):
            u = fp.stem.split("_")[0]
            analysts.add("TJ_Research" if u == "TJ" else u)
        return {"analysts": sorted(analysts), "sectors": self._sectors()}

    def _sectors(self) -> dict:
        """
        从 data/sector_map.json 加载行业-股票映射。
        
        按 (sector / industry) 组合分组，仅保留股票数 >= 3 的板块，
        按规模降序排列。用于角色代入选股时的股票池来源。
        """
        fp = Path("data/sector_map.json")
        if not fp.exists():
            return {}
        raw = json.loads(fp.read_text(encoding="utf-8"))
        groups: dict = defaultdict(list)
        for ticker, v in raw.items():
            label = f'{v.get("sector","Other")} / {v.get("industry","Other")}'
            groups[label].append(ticker)
        return {k: sorted(v) for k, v in sorted(groups.items(), key=lambda x: -len(x[1])) if len(v) >= 3}

    def _render_html(self, data: dict) -> str:
        """
        生成角色代入选股界面的 HTML（模板不存在时的 fallback）。

        HTML 结构概览:
            1. 标题栏 — "角色代入选股"
            2. 三栏选择区: 分析师下拉框 + 行业板块下拉框 + 生成方案按钮
            3. 手动加减输入框（+TICKER / -TICKER 语法）
            4. 当前股票池预览 + 隐层 JSON 数据 + 结果展示区
        """
        analysts_opts = "".join(f'<option>{a}</option>' for a in data["analysts"])
        sectors = data.get("sectors", {})
        sector_opts = "".join(f'<option value="{k}">{k} ({len(v)}只)</option>' for k, v in sectors.items())
        # 第一个行业的股票
        first_sector = list(sectors.keys())[0] if sectors else ""
        first_stocks = ", ".join(sectors.get(first_sector, [])[:15]) if first_sector else ""
        return f'''<div class="card-title">角色代入选股</div>
<div class="grid grid-3 mb-sm">
  <div><div class="text-secondary mb-sm">分析师</div><select id="rp_analyst">{analysts_opts}</select></div>
  <div><div class="text-secondary mb-sm">行业板块</div><select id="rp_sector" data-action="update-pool" data-card="role_picker">{sector_opts}</select></div>
  <div style="display:flex;align-items:flex-end"><button class="btn btn-primary" style="width:100%" data-action="gen-pick" data-card="role_picker">生成方案</button></div>
</div>
<div class="text-secondary mb-sm">手动加减 <input id="rp_custom" style="width:100%;margin-top:4px" placeholder="可选: LRCX, AMAT, -INTC" /></div>
<div id="rp_pool" class="text-secondary" style="font-size:11px;word-break:break-all">池内: {first_stocks}</div>
<div id="rp_sectors" style="display:none">{json.dumps(sectors)}</div></div>
<div id="rp_result" style="margin-top:12px"></div>'''


@register
class PortfolioCard(Card):
    """
    持股顾问卡片。

    用户输入或上传持仓信息（股票代码、股数、成本价），
    系统结合分析师信号、板块轮动、准确率等数据给出持仓建议。

    属性:
        name="portfolio"          — 唯一标识
        tab="insights"            — 属于分析洞察标签页
        endpoint="/api/portfolio" — API 路由
        refresh=0（默认）          — 不自动刷新

    get_data() 返回结构:
        {
            "analysts": {                     # 分析师 → 30日胜率(%)
                "TJ_Research": 65,
                ...
            }
        }
    """
    name = "portfolio"
    def get_data(self, **params) -> dict:
        acc = {}
        for fp in Path("data/accuracy").glob("*_accuracy.json"):
            u = fp.stem.replace("_accuracy", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            wr = d.get("returns_30d", {}).get("win_rate")
            if wr is not None:
                acc[u] = round(wr * 100)
        return {"analysts": acc}

    def _render_html(self, data: dict) -> str:
        """
        生成持股顾问界面的 HTML（模板不存在时的 fallback）。

        HTML 结构概览:
            1. 标题栏 — "持股顾问"
            2. 持仓输入区 — 文本输入框（持股文本描述）
            3. 操作按钮 — "分析持仓" 按钮
            4. 结果展示区（pf_result div）
            5. 支持图片/CSV 上传
        """
        return '''<div class="card-title">持股顾问</div>
<div class="mb-sm" style="display:flex;gap:6px">
  <textarea id="pf_text" rows="3" style="flex:1;font-size:12px;padding:8px" placeholder="输入持仓: NVDA 100股 成本$110&#10;AVGO 50股 成本$320&hellip;"></textarea>
</div>
<div class="flex" style="gap:8px">
  <button class="btn btn-primary" data-action="analyze-portfolio" data-card="portfolio">分析持仓</button>
  <span class="text-secondary" style="font-size:11px">也支持上传图片/CSV</span>
</div>
<div id="pf_result" style="margin-top:12px"></div>'''
