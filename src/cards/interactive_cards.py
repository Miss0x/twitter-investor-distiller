"""Daemon + Telegram + 角色代入 + 持仓顾问 — 交互卡片"""
import json, time
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class DaemonCard(Card):
    name = "daemon"; tab = "dashboard"; endpoint = "/api/daemon"; refresh = 5

    def get_data(self, **params) -> dict:
        state = Path("data/auto_scheduler_state.json")
        running = getattr(self, "_proc", None) is not None
        last_id = json.loads(state.read_text()).get("last_id", 0) if state.exists() else 0
        try:
            from src.storage.database import db
            from src.storage.models import PipelineTask
            db.init_db(); s = db.get_session()
            cnt = s.query(PipelineTask).filter(PipelineTask.task_type == "analyze", PipelineTask.created_at >= time.strftime("%Y-%m-%d")).count()
            s.close()
        except: cnt = 0
        return {"running": running, "last_id": last_id, "today": cnt, "budget": 20}

    def _render_html(self, data: dict) -> str:
        status = "运行中" if data["running"] else "未启动"
        color = "ok" if data["running"] else ""
        return f'''<div class="flex-between">
  <div><div class="card-title">实时监控</div><div class="flex"><div class="status-dot {color}"></div><span style="font-size:20px;font-weight:500">{status}</span></div></div>
  <div style="text-align:right"><div class="metric-value">{data["today"]} / {data["budget"]}</div><div class="metric-label">今日任务</div></div>
  <div><button class="btn {'btn-danger' if data['running'] else 'btn-primary'}" onclick="fetch('/cards/daemon/action',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{action:'toggle'}})}})">{'停止' if data['running'] else '启动'}</button></div>
</div>'''


@register
class TelegramCard(Card):
    name = "telegram"; tab = "dashboard"; endpoint = "/api/telegram"

    def get_data(self, **params) -> dict:
        fp = Path("data/telegram_config.json")
        cfg = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
        return {"configured": bool(cfg.get("bot_token")), "chat_id": cfg.get("chat_id", "")}

    def _render_html(self, data: dict) -> str:
        status = "已配置" if data["configured"] else "未配置"
        color = "ok" if data["configured"] else "warn"
        return f'<div class="card-title">Telegram 通知</div><div class="flex"><div class="status-dot {color}"></div><span style="font-size:14px;font-weight:500">{status}</span></div>'


@register
class RolePickerCard(Card):
    name = "role_picker"; tab = "insights"; endpoint = "/api/role_picker"

    def get_data(self, **params) -> dict:
        analysts = set()
        for fp in Path("data/pipeline").glob("*_analyzed_cleaned.json"):
            u = fp.stem.split("_")[0]
            analysts.add("TJ_Research" if u == "TJ" else u)
        return {"analysts": sorted(analysts), "sectors": self._sectors()}

    def _sectors(self) -> dict:
        fp = Path("data/sector_map.json")
        if not fp.exists(): return {}
        d = json.loads(fp.read_text(encoding="utf-8"))
        groups: dict = defaultdict(list)
        for ticker, v in d.items():
            label = f'{v.get("sector","Other")} / {v.get("industry","Other")}'
            groups[label].append(ticker)
        from collections import defaultdict
        return {k: sorted(v) for k, v in sorted(groups.items(), key=lambda x: -len(x[1])) if len(v) >= 3}

    def _render_html(self, data: dict) -> str:
        analysts_opts = "".join(f'<option>{a}</option>' for a in data["analysts"])
        sector_opts = "".join(f'<option value="{k}">{k} ({len(v)}只)</option>' for k, v in data.get("sectors", {}).items())
        return f'''<div class="card-title">角色代入选股</div>
<div class="grid grid-3 mb-sm">
  <div><div class="text-secondary mb-sm">分析师</div><select>{analysts_opts}</select></div>
  <div><div class="text-secondary mb-sm">行业板块</div><select id="rp_sector" onchange="updatePool()">{sector_opts}</select></div>
  <div style="display:flex;align-items:flex-end"><button class="btn btn-primary" style="width:100%" onclick="genPick()">生成方案</button></div>
</div>
<div class="text-secondary mb-sm">手动加减股票 <input style="width:100%;margin-top:4px" placeholder="可选: LRCX, AMAT, -INTC" /></div>
<div id="rp_pool" class="text-secondary" style="font-size:11px"></div>
<div id="rp_result"></div>'''


@register
class PortfolioCard(Card):
    name = "portfolio"; tab = "insights"; endpoint = "/api/portfolio"

    def get_data(self, **params) -> dict:
        acc = {}
        for fp in Path("data/accuracy").glob("*_accuracy.json"):
            u = fp.stem.replace("_accuracy", "")
            d = json.loads(fp.read_text(encoding="utf-8"))
            wr = d.get("returns_30d", {}).get("win_rate")
            if wr is not None: acc[u] = round(wr * 100)
        return {"analysts": acc}

    def _render_html(self, data: dict) -> str:
        return '''<div class="card-title">持股顾问</div>
<div class="flex mb-sm">
  <button class="btn" style="border-color:var(--text-primary)">CSV 文件</button>
  <button class="btn">文字输入</button>
  <button class="btn">截图上传</button>
  <div style="flex:1"></div>
  <button class="btn btn-primary">分析</button>
</div>
<div style="padding:30px;border:0.5px dashed var(--border-tertiary);border-radius:var(--radius-md);text-align:center" class="text-secondary">拖放文件或点击上传</div>'''
