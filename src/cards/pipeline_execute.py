"""流水线执行 + 画像生成 — 完整交互卡片"""
import json
from src.cards.base import Card
from src.cards import register


@register
class PipelineExecuteCard(Card):
    name = "pipeline_execute"
    tab = "pipeline"
    endpoint = "/api/pipeline_execute"
    refresh = 15

    def get_data(self, **params) -> dict:
        try:
            from src.storage.database import db
            from src.storage.models import PipelineTask
            db.init_db()
            s = db.get_session()
            tasks = s.query(PipelineTask).order_by(PipelineTask.id.desc()).limit(200).all()
            grouped = {}
            for t in tasks:
                p = json.loads(t.payload) if t.payload else {}
                item = {"id": t.id, "task_type": t.task_type, "status": t.status,
                        "payload": p, "error_msg": t.error_msg,
                        "created_at": str(t.created_at)[:16] if t.created_at else ""}
                grouped.setdefault(t.task_type, []).append(item)
            s.close()
            from src.pipeline.task_executor import is_running, get_progress
            return {
                "groups": grouped,
                "running": is_running(),
                "progress": get_progress(),
                "types": ["filter", "analyze", "fetch_price", "fetch_crypto", "portrait", "clean"],
            }
        except Exception:
            return {"groups": {}, "running": False, "progress": {}, "types": []}

    def _render_html(self, data: dict) -> str:
        groups = data.get("groups", {})
        running = data.get("running", False)
        progress = data.get("progress", {})
        types = data.get("types", [])

        type_tabs = "".join(
            f'<button class="tab pe-tab" onclick="loadType(\'{t}\')" id="tab-{t}">{t}</button>'
            for t in types
        )
        status_bar = f'执行中: {progress.get("msg","")} ({progress.get("done",0)}/{progress.get("total",0)})' if running else "空闲"

        containers = ""
        for t in types:
            items = groups.get(t, [])
            pending = [i for i in items if i["status"] == "pending"]
            failed = [i for i in items if i["status"] == "failed"]
            done = [i for i in items if i["status"] == "done"]

            # Pending tasks
            pending_rows = "".join(
                f'<tr><td><input type="checkbox" value="{p["id"]}" class="pe-cb-{t}" /></td>'
                f'<td style="font-size:11px">#{p["id"]}</td>'
                f'<td style="font-size:11px">{_format_label(t, p["payload"])}</td></tr>'
                for p in pending[:30]
            ) if pending else '<tr><td colspan="3" class="text-secondary">无待办</td></tr>'

            # Failed tasks
            failed_rows = "".join(
                f'<tr><td style="font-size:11px">#{f["id"]}</td>'
                f'<td style="font-size:11px">{f.get("error_msg","?")[:50]}</td>'
                f'<td><button class="btn" style="font-size:10px;padding:2px 6px" onclick="retryTask({f["id"]})">重试</button> '
                f'<button class="btn" style="font-size:10px;padding:2px 6px" onclick="skipTask({f["id"]})">跳过</button></td></tr>'
                for f in failed[:10]
            ) if failed else ''

            counters = f'待办 {len(pending)} | 完成 {len(done)} | 失败 {len(failed)}'
            containers += f'''<div id="pe-type-{t}" class="pe-container" style="display:none">
<div class="flex-between mb-sm"><span class="text-secondary" style="font-size:11px">{counters}</span>
<span><button class="btn" style="font-size:10px;padding:2px 6px" onclick="selectAll('{t}')">全选</button>
<button class="btn" style="font-size:10px;padding:2px 6px" onclick="clearAll('{t}')">取消</button>
<button class="btn" style="font-size:10px;padding:2px 6px" onclick="execPipeline('{t}')">▶ 执行选中</button></span></div>
<table class="data"><tr><th style="width:24px"></th><th>ID</th><th>详情</th></tr>{pending_rows}</table>
{f'<div class="mt-sm"><span class="text-secondary" style="font-size:11px">失败 ({len(failed)})</span><table class="data">{failed_rows}</table></div>' if failed else ''}
</div>'''

        return f'''<div class="card-title">流水线执行</div>
<div class="flex-between mb-sm"><div class="flex"><div class="status-dot {"ok" if running else ""}"></div><span style="font-size:12px">{status_bar}</span></div></div>
<div class="mb-sm" style="display:flex;gap:4px;flex-wrap:wrap">{type_tabs}</div>
<div style="display:flex;gap:6px;margin-bottom:8px">
  <button class="btn" onclick="filterNewTweets()" style="font-size:11px">🔍 扫描新推文</button>
  <button class="btn" onclick="seedTasks()" style="font-size:11px">🌱 种子任务</button>
  <span id="pe-msg" class="text-secondary" style="font-size:11px"></span>
</div>
{containers}
<script>
var PE_ACTIVE = 'filter';
function loadType(t){{ 
  PE_ACTIVE = t;
  document.querySelectorAll('.pe-container').forEach(e=>e.style.display='none');
  document.querySelectorAll('.pe-tab').forEach(e=>e.classList.remove('active'));
  var c=document.getElementById('pe-type-'+t); if(c) c.style.display='block';
  var tab=document.getElementById('tab-'+t); if(tab) tab.classList.add('active');
}}
function selectAll(t){{ document.querySelectorAll('.pe-cb-'+t).forEach(c=>c.checked=true); }}
function clearAll(t){{ document.querySelectorAll('.pe-cb-'+t).forEach(c=>c.checked=false); }}
async function execPipeline(t){{
  var ids=[];
  document.querySelectorAll('.pe-cb-'+t+':checked').forEach(c=>ids.push(c.value));
  if(!ids.length)return;
  var s=document.getElementById('pe-msg'); s.innerText='执行中...';
  try{{
    var r=await fetch('/pipeline/tasks/execute',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{task_ids:ids}})}});
    s.innerText='已提交 '+ids.length+' 个任务';
    setTimeout(()=>location.reload(),2000);
  }}catch(e){{s.innerText='错误';}}
}}
async function retryTask(id){{
  await fetch('/pipeline/tasks/'+id+'/retry',{{method:'POST'}});
  location.reload();
}}
async function skipTask(id){{
  await fetch('/pipeline/tasks/'+id+'/skip',{{method:'POST'}});
  location.reload();
}}
async function filterNewTweets(){{
  var s=document.getElementById('pe-msg'); s.innerText='扫描中...';
  await fetch('/pipeline/filter',{{method:'POST'}});
  s.innerText='完成'; setTimeout(()=>location.reload(),1500);
}}
async function seedTasks(){{
  await fetch('/pipeline/tasks/seed',{{method:'POST'}});
  location.reload();
}}
loadType('filter');
</script>'''


def _format_label(task_type: str, payload: dict) -> str:
    if task_type == "analyze" and payload.get("tweet_id"):
        return f'#{payload["tweet_id"]} | {payload.get("text","")[:40]}'
    elif task_type in ("fetch_price", "fetch_crypto"):
        return payload.get("ticker", "?")
    elif task_type == "portrait":
        return f'{payload.get("username","?")} ({payload.get("tweet_count",0)}条 · {payload.get("label","")})'
    elif task_type == "filter":
        return payload.get("action", "filter_latest")
    return payload.get("tweet_id", str(payload)[:40])


@register
class PortraitGenerateCard(Card):
    name = "portrait_generate"
    tab = "portraits"
    endpoint = "/api/portrait_generate"
    refresh = 0

    def get_data(self, **params) -> dict:
        try:
            from src.storage.database import db
            from src.storage.models import PipelineTask
            db.init_db()
            s = db.get_session()
            portrait_tasks = s.query(PipelineTask).filter(
                PipelineTask.task_type == "portrait"
            ).order_by(PipelineTask.id.desc()).limit(20).all()
            items = [{"id": t.id, "status": t.status,
                      "payload": __import__('json').loads(t.payload) if t.payload else {},
                      "created_at": str(t.created_at)[:16] if t.created_at else ""}
                     for t in portrait_tasks]
            s.close()
        except Exception:
            items = []
        return {"tasks": items, "users": ["TJ_Research", "dearbaibabybus"]}

    def _render_html(self, data: dict) -> str:
        users = data.get("users", [])
        pending = [t for t in data.get("tasks", []) if t["status"] == "pending"]
        done = [t for t in data.get("tasks", []) if t["status"] == "done"]
        user_opts = "".join(f'<option>{u}</option>' for u in users)
        return f'''<div class="card-title">画像生成</div>
<div class="mb-sm"><span class="tag tag-ok">已完成: {len(done)}</span> <span class="tag tag-warn">待处理: {len(pending)}</span></div>
<div class="flex mb-sm" style="gap:8px">
  <select id="pg_user">{user_opts}</select>
  <button class="btn btn-primary" onclick="genPortrait()">生成画像</button>
  <span id="pg_status" class="text-secondary" style="font-size:11px"></span>
</div>
<div class="text-secondary" style="font-size:11px">需先完成 analyze 任务。也可用流水线执行中的 portrait 类型批量生成。</div>
<script>
async function genPortrait(){{
  var u=document.getElementById('pg_user').value;
  var s=document.getElementById('pg_status'); s.innerText='生成中...';
  try{{
    var r=await fetch('/cards/portrait_generate/action',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{user:u}})}});
    var d=await r.json();
    s.innerText=d.ok?'完成':'失败: '+(d.error||'');
    setTimeout(()=>location.reload(),2000);
  }}catch(e){{s.innerText='网络错误';}}
}}
</script>'''
