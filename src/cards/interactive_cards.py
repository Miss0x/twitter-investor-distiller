"""Daemon + Telegram + 角色代入 + 持仓顾问 — 交互卡片"""
import json, time
from pathlib import Path
from collections import defaultdict
from src.cards.base import Card
from src.cards import register


@register
class DaemonCard(Card):
    name = "daemon"
    tab = "dashboard"
    endpoint = "/api/daemon"
    refresh = 5

    def get_data(self, **params) -> dict:
        state = Path("data/auto_scheduler_state.json")
        running = json.loads(state.read_text()).get("running", False) if state.exists() else False
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
  <div><div class="card-title">实时 API 采集</div><div class="flex"><div class="status-dot {color}"></div><span style="font-size:20px;font-weight:500">{status}</span></div><div class="text-secondary" style="font-size:11px">twitterapi.io · 60s 轮转 · 备灾浏览器爬虫</div></div>
  <div style="text-align:right"><div class="metric-value">{data["today"]} / {data["budget"]}</div><div class="metric-label">今日拉取</div></div>
  <button class="btn {'btn-danger' if data['running'] else 'btn-primary'}" id="daemon-btn" onclick="toggleDaemon()">{'停止' if data['running'] else '启动'}</button>
</div>'''


@register
class TelegramCard(Card):
    name = "telegram"
    tab = "dashboard"
    endpoint = "/api/telegram"

    def get_data(self, **params) -> dict:
        fp = Path("data/telegram_config.json")
        cfg = json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}
        return {"configured": bool(cfg.get("bot_token")), "chat_id": cfg.get("chat_id", ""),
                "token_preview": (cfg.get("bot_token", "")[:12] + "...") if cfg.get("bot_token") else ""}

    def _render_html(self, data: dict) -> str:
        status = "已配置" if data["configured"] else "未配置"
        color = "ok" if data["configured"] else "warn"
        token_hint = data.get("token_preview", "")
        return f'''<div class="card-title">Telegram 通知</div>
<div class="flex mb-sm"><div class="status-dot {color}"></div><span style="font-size:14px;font-weight:500">{status}</span></div>
<div class="text-secondary mb-sm" style="font-size:11px">{token_hint} → Chat: {data["chat_id"]}</div>
<div class="flex" style="gap:8px">
  <input id="tg_token" placeholder="Bot Token" style="flex:1;font-size:12px;padding:4px 8px" />
  <input id="tg_chatid" placeholder="Chat ID" style="width:140px;font-size:12px;padding:4px 8px" />
  <button class="btn" onclick="sendTestMsg()">测试</button>
  <button class="btn" onclick="saveTelegram()">保存</button>
</div>
<script>
async function sendTestMsg(){{
  var t=document.getElementById("tg_token").value,c=document.getElementById("tg_chatid").value;
  if(!t||!c)return;
  await fetch("/cards/telegram/action",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{token:t,chat_id:c,action:"test"}})}});
  alert("测试消息已发送，请检查 Telegram");
}}
async function saveTelegram(){{
  var t=document.getElementById("tg_token").value,c=document.getElementById("tg_chatid").value;
  if(!t||!c)return;
  await fetch("/cards/telegram/action",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{token:t,chat_id:c}})}});
  location.reload();
}}
</script>'''


@register
class RolePickerCard(Card):
    name = "role_picker"
    tab = "insights"
    endpoint = "/api/role_picker"

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
        return {k: sorted(v) for k, v in sorted(groups.items(), key=lambda x: -len(x[1])) if len(v) >= 3}

    def _render_html(self, data: dict) -> str:
        analysts_opts = "".join(f'<option>{a}</option>' for a in data["analysts"])
        sectors = data.get("sectors", {})
        sector_opts = "".join(f'<option value="{k}">{k} ({len(v)}只)</option>' for k, v in sectors.items())
        # 第一个行业的股票
        first_sector = list(sectors.keys())[0] if sectors else ""
        first_stocks = ", ".join(sectors.get(first_sector, [])[:15]) if first_sector else ""
        return f'''<div class="card-title">角色代入选股</div>
<div class="grid grid-3 mb-sm">
  <div><div class="text-secondary mb-sm">分析师</div><select id="rp_analyst">{analysts_opts}</select></div>
  <div><div class="text-secondary mb-sm">行业板块</div><select id="rp_sector" onchange="updatePool()">{sector_opts}</select></div>
  <div style="display:flex;align-items:flex-end"><button class="btn btn-primary" style="width:100%" onclick="generatePick()">生成方案</button></div>
</div>
<div class="text-secondary mb-sm">手动加减 <input id="rp_custom" style="width:100%;margin-top:4px" placeholder="可选: LRCX, AMAT, -INTC" /></div>
<div id="rp_pool" class="text-secondary" style="font-size:11px;word-break:break-all">池内: {first_stocks}</div>
<div id="rp_result" style="margin-top:12px"></div>
<script>
var SECTORS = {json.dumps(sectors)};
function updatePool(){{ var s=document.getElementById("rp_sector").value; var t=SECTORS[s]||[]; document.getElementById("rp_pool").innerText="池内: "+t.join(", "); }}
async function generatePick(){{ 
  var btn=event.target; btn.disabled=true; btn.innerText="生成中...";
  document.getElementById("rp_result").innerHTML='<div class="flex"><div class="spinner"></div><span class="text-secondary">AI 思考中...</span></div>';
  try{{
    var r=await fetch("/cards/role_picker/action",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{analyst:document.getElementById("rp_analyst").value,sector:document.getElementById("rp_sector").value,custom:document.getElementById("rp_custom").value}})}});
    var d=await r.json();
    document.getElementById("rp_result").innerHTML=d.ok?d.html:'<div class="text-secondary">错误: '+d.error+"</div>";
  }}catch(e){{document.getElementById("rp_result").innerHTML='<div class="text-secondary">网络错误</div>';}}
  btn.disabled=false; btn.innerText="生成方案";
}}
</script>'''


@register
class PortfolioCard(Card):
    name = "portfolio"
    tab = "insights"
    endpoint = "/api/portfolio"

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
<div class="mb-sm" style="display:flex;gap:6px">
  <textarea id="pf_text" rows="3" style="flex:1;font-size:12px;padding:8px" placeholder="输入持仓: NVDA 100股 成本$110&#10;AVGO 50股 成本$320&hellip;"></textarea>
</div>
<div class="flex" style="gap:8px">
  <button class="btn btn-primary" onclick="analyzePortfolio()">分析持仓</button>
  <span class="text-secondary" style="font-size:11px">也支持上传图片/CSV</span>
</div>
<div id="pf_result" style="margin-top:12px"></div>
<script>
async function analyzePortfolio(){
  var v=document.getElementById("pf_text").value;
  if(!v.trim())return;
  var btn=event.target; btn.disabled=true; btn.innerText="分析中...";
  document.getElementById("pf_result").innerHTML='<div class="flex"><div class="spinner"></div><span class="text-secondary">AI 分析中...</span></div>';
  try{
    var r=await fetch("/cards/portfolio/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:v})});
    var d=await r.json();
    document.getElementById("pf_result").innerHTML=d.ok?d.html:'<div class="text-secondary">错误: '+d.error+"</div>";
  }catch(e){document.getElementById("pf_result").innerHTML='<div class="text-secondary">网络错误</div>';}
  btn.disabled=false; btn.innerText="分析持仓";
}
</script>'''
