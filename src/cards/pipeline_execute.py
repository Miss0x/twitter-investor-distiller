"""流水线执行 + 画像生成 — 完整交互卡片"""
import csv
import html
import json
from pathlib import Path
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
            from collections import Counter
            type_counts = Counter(t.task_type for t in tasks)

            # ── 数据清洗：加载别名统计 ──
            alias_stats = {"confirmed": 0, "pending": 0, "skipped": 0, "total": 0}
            try:
                import csv
                alias_fp = Path("data/stock_alias.csv")
                if alias_fp.exists():
                    reader = csv.reader(alias_fp.read_text(encoding="utf-8").splitlines())
                    for row in reader:
                        if not row or not row[0] or row[0].startswith("#"):
                            continue
                        alias_stats["total"] += 1
                        ticker = row[1].strip() if len(row) >= 2 else ""
                        notes = row[2].strip() if len(row) >= 3 else ""
                        if ticker:
                            alias_stats["confirmed"] += 1
                        elif notes.startswith("SKIP"):
                            alias_stats["skipped"] += 1
                        else:
                            alias_stats["pending"] += 1
            except: pass

            return {
                "groups": grouped,
                "running": is_running(),
                "progress": get_progress(),
                "type_counts": dict(type_counts),
                "types": ["filter", "analyze", "fetch_price", "fetch_crypto", "portrait", "clean"],
                "alias_stats": alias_stats,
            }
        except Exception:
            return {"groups": {}, "running": False, "progress": {}, "types": [], "alias_stats": {}}

    def _render_html(self, data: dict) -> str:
        groups = data.get("groups", {})
        running = data.get("running", False)
        progress = data.get("progress", {})
        tc = data.get("type_counts", {})
        type_names = {
            "filter": "过滤筛选", "analyze": "推文分析", "fetch_price": "股价拉取",
            "fetch_crypto": "加密货币", "portrait": "画像生成", "clean": "数据清洗",
        }
        types = list(type_names.keys())

        # ── 批量查推文文本，注入到 filter / analyze payload 中 ──
        _enrich_tweet_texts(groups)

        type_tabs = "".join(
            f'<button class="tab pe-tab" onclick="loadTypePE(\'{t}\')" id="tab-{t}">{type_names[t]}</button>'
            for t in types
        )
        status_bar = f'执行中: {progress.get("msg","")} ({progress.get("done",0)}/{progress.get("total",0)})' if running else "空闲"
        type_tags = "".join(
            f'<span class="tag tag-ok">{type_names.get(t,t)}: {tc.get(t,0)}</span>'
            for t in types if tc.get(t, 0) > 0
        )

        containers = ""
        for t in types:
            items = groups.get(t, [])
            if t == "clean":
                # ── 数据清洗：资产代码库（完整表格 + 校准按钮） ──
                aliases_list = []
                afp = Path("data/stock_alias.csv")
                if afp.exists():
                    reader = csv.reader(afp.read_text(encoding="utf-8").splitlines())
                    for row in reader:
                        if not row or not row[0] or row[0].startswith("#"): continue
                        a = row[0].strip()
                        tkr = row[1].strip() if len(row) >= 2 else ""
                        nts = row[2].strip() if len(row) >= 3 else ""
                        if a: aliases_list.append({"alias": a, "ticker": tkr, "type": nts})
                confirmed = [a for a in aliases_list if a["ticker"]]
                pending = [a for a in aliases_list if not a["ticker"] and not a.get("type","").startswith("SKIP")]
                skipped = [a for a in aliases_list if not a["ticker"] and a.get("type","").startswith("SKIP")]

                confirmed_rows = "".join(
                    f'<tr><td style="font-size:11px">{a["alias"]}</td><td style="font-weight:500">{a["ticker"]}</td><td style="font-size:11px;color:var(--text-secondary)">{a.get("type","")}</td><td style="text-align:right"><button class="btn" style="font-size:10px;padding:1px 6px" onclick="editAliasRow(\'{html.escape(a["alias"])}\',\'{html.escape(a["ticker"])}\',\'{html.escape(a.get("type",""))}\')">编辑</button> <button class="btn btn-danger" style="font-size:10px;padding:1px 6px" onclick="deleteAlias(\'{html.escape(a["alias"])}\')">删除</button></td></tr>'
                    for a in confirmed[:50]
                ) if confirmed else '<tr><td colspan="4" class="text-secondary">暂无已确认映射</td></tr>'

                pending_rows = "".join(
                    f'<tr style="background:rgba(239,159,39,0.05)"><td style="font-size:11px;font-weight:500">{a["alias"]}</td><td style="font-size:11px;color:var(--text-secondary)">{a.get("type","")}</td><td style="text-align:right"><button class="btn" style="font-size:10px;padding:1px 6px" onclick="fillAliasForm(\'{html.escape(a["alias"])}\',\'{html.escape(a.get("type",""))}\')">填代码</button> <button class="btn" style="font-size:10px;padding:1px 6px;border-color:var(--text-tertiary);color:var(--text-tertiary)" onclick="skipAlias(\'{html.escape(a["alias"])}\')">跳过</button> <button class="btn btn-danger" style="font-size:10px;padding:1px 6px" onclick="deleteAlias(\'{html.escape(a["alias"])}\')">删除</button></td></tr>'
                    for a in pending[:30]
                ) if pending else '<tr><td colspan="4" class="text-secondary" style="color:var(--text-success)">全部确认完毕</td></tr>'

                skipped_rows = "".join(
                    f'<tr style="opacity:0.5"><td style="font-size:11px">{a["alias"]}</td><td style="font-size:11px;color:var(--text-secondary)">{a.get("type","").replace("SKIP|","",1)}</td><td style="text-align:right"><button class="btn" style="font-size:10px;padding:1px 6px" onclick="unskipAlias(\'{html.escape(a["alias"])}\')">恢复</button></td></tr>'
                    for a in skipped[:30]
                )

                containers += f'''<div id="pe-type-clean" class="pe-container" style="display:none">
<div class="flex-between mb-sm"><span style="font-size:12px;font-weight:500">资产代码库</span><button class="btn" onclick="runCleanAlias()" style="font-size:11px">🔄 运行校准</button></div>
<div class="mb-sm"><span id="clean_status" class="text-secondary" style="font-size:11px"></span></div>
<div class="grid grid-4 mb-sm">
  <div class="metric"><div class="metric-label">总映射</div><div class="metric-value">{len(aliases_list)}</div></div>
  <div class="metric"><div class="metric-label">已确认</div><div class="metric-value" style="color:var(--text-success)">{len(confirmed)}</div></div>
  <div class="metric"><div class="metric-label">待判断</div><div class="metric-value" style="color:var(--text-warning)">{len(pending)}</div></div>
  <div class="metric"><div class="metric-label">已跳过</div><div class="metric-value" style="color:var(--text-tertiary)">{len(skipped)}</div></div>
</div>
<div class="flex mb-sm" style="gap:4px;flex-wrap:wrap">
  <input id="aa_alias" placeholder="别名" style="flex:1;min-width:80px;font-size:11px;padding:4px 6px" />
  <input id="aa_ticker" placeholder="代码" style="flex:1;min-width:60px;font-size:11px;padding:4px 6px" />
  <input id="aa_notes" placeholder="备注" style="flex:1;min-width:60px;font-size:11px;padding:4px 6px" />
  <button class="btn btn-primary" onclick="addAlias()" style="font-size:11px;padding:4px 10px" id="btn_aa_submit">添加</button>
</div>
<input type="hidden" id="aa_old_alias" value="" />
<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-primary)">已确认映射 ({len(confirmed)}条)</span></div>
<table class="data"><tr><th>别名</th><th>代码</th><th>备注</th><th style="text-align:right">操作</th></tr>{confirmed_rows}</table>
<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-warning)">待人工判断 ({len(pending)}条)</span></div>
<table class="data"><tr><th>别名</th><th>系统标注</th><th style="text-align:right">操作</th></tr>{pending_rows}</table>
{skipped_rows and f'<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-tertiary)">已跳过 ({len(skipped)}条)</span></div><table class="data"><tr><th>别名</th><th>系统标注</th><th style="text-align:right">操作</th></tr>' + skipped_rows + '</table>'}
<div class="text-secondary mt-sm" style="font-size:10px">提示：点"填代码"自动回填表单，输入 ticker 后提交即可移入已确认列表。跳过则暂不处理。</div>
</div>'''
                continue
            pending = [i for i in items if i["status"] == "pending"]
            failed = [i for i in items if i["status"] == "failed"]
            done = [i for i in items if i["status"] == "done"]

            pending_rows = "".join(
                f'<tr><td><input type="checkbox" value="{p["id"]}" class="pe-cb-{t}" /></td>'
                f'<td style="font-size:11px">#{p["id"]}</td>'
                f'<td style="font-size:11px">{_format_label(t, p["payload"])}</td></tr>'
                for p in pending[:30]
            ) if pending else '<tr><td colspan="3" class="text-secondary">无待办</td></tr>'

            failed_rows = "".join(
                f'<tr><td style="font-size:11px">#{f["id"]}</td>'
                f'<td style="font-size:11px">{f.get("error_msg","?")[:50]}</td>'
                f'<td><button class="btn" style="font-size:10px;padding:2px 6px" onclick="retryTaskPE({f["id"]})">重试</button> '
                f'<button class="btn" style="font-size:10px;padding:2px 6px" onclick="skipTaskPE({f["id"]})">跳过</button></td></tr>'
                for f in failed[:10]
            ) if failed else ''

            containers += f'''<div id="pe-type-{t}" class="pe-container" style="display:none">
<div class="flex-between mb-sm"><span class="text-secondary" style="font-size:11px">待办 {len(pending)} | 完成 {len(done)} | 失败 {len(failed)}</span>
<span><button class="btn" style="font-size:10px;padding:2px 6px" onclick="selectAllPE('{t}')">全选</button>
<button class="btn" style="font-size:10px;padding:2px 6px" onclick="clearAllPE('{t}')">取消</button>
<button class="btn" style="font-size:10px;padding:2px 6px" onclick="execPipeline('{t}')">▶ 执行选中</button></span></div>
<table class="data"><tr><th style="width:24px"></th><th>ID</th><th>详情</th></tr>{pending_rows}</table>
{f'<div class="mt-sm"><span class="text-secondary" style="font-size:11px">失败 ({len(failed)})</span><table class="data">{failed_rows}</table></div>' if failed else ''}
</div>'''

        return f'''<div class="card-title">流水线执行</div>
<div class="flex-between mb-sm"><div class="flex"><div class="status-dot {"ok" if running else ""}"></div><span style="font-size:12px">{status_bar}</span></div></div>
<div class="mb-sm" style="display:flex;gap:4px;flex-wrap:wrap">{type_tags}</div>
<div class="mb-sm" style="display:flex;gap:4px;flex-wrap:wrap">{type_tabs}</div>
<div style="display:flex;gap:6px;margin-bottom:8px">
  <button class="btn" onclick="seedTasksPE()" style="font-size:11px">🌱 种子任务</button>
  <span id="pe-msg" class="text-secondary" style="font-size:11px"></span>
</div>
{containers}
</div>'''


def _enrich_tweet_texts(groups: dict) -> None:
    """批量查询推文文本，注入到 filter / analyze 任务的 payload 中"""
    # 收集所有 tweet_id
    tweet_ids = set()
    for items in groups.values():
        for item in items:
            p = item.get("payload", {}) or {}
            tid = p.get("tweet_id")
            if tid and isinstance(tid, int) and item.get("task_type") in ("filter", "analyze"):
                tweet_ids.add(tid)
    if not tweet_ids:
        return

    # 批量 DB 查询（分片，避免 SQLite 变量数超 999 限制）
    try:
        import sqlite3
        conn = sqlite3.connect("data/twitter_data.db")
        tweet_ids_list = list(tweet_ids)
        text_map = {}
        for start in range(0, len(tweet_ids_list), 900):
            chunk = tweet_ids_list[start:start+900]
            placeholders = ",".join(["?"] * len(chunk))
            rows = conn.execute(
                f"SELECT id, COALESCE(text,'') as text, COALESCE(user_id,'') as user_id FROM tweets WHERE id IN ({placeholders})",
                tuple(chunk)
            ).fetchall()
            text_map.update({row[0]: {"text": row[1], "user_id": row[2]} for row in rows})
        conn.close()
    except Exception:
        return

    # 注入到 payload
    for items in groups.values():
        for item in items:
            p = item.get("payload", {}) or {}
            tid = p.get("tweet_id")
            if tid in text_map:
                p["_text"] = text_map[tid]["text"]
                p["_user"] = text_map[tid]["user_id"]


def _format_label(task_type: str, payload: dict) -> str:
    """将任务 payload 转为可读中文描述"""
    # filter: 优先展示注入的推文文本
    if task_type == "filter":
        txt = payload.get("_text", "")
        if txt:
            prefix = f'@{payload.get("_user","")} ' if payload.get("_user") else ""
            return f'{prefix}{html.escape(txt[:50])}{"..." if len(txt)>50 else ""}'
        # 没有文本则显示 action 中文名
        action = payload.get("action", "")
        action_labels = {
            "filter_single": "单条过滤",
            "filter_latest": "最新推文过滤",
            "filter_media": "媒体过滤",
            "filter_replies": "回复过滤",
        }
        return action_labels.get(action, action or "推文过滤")
    elif task_type == "analyze":
        tid = payload.get("tweet_id", "")
        text = payload.get("_text", "") or payload.get("text", "") or ""
        if tid and text:
            return f'#{tid} | {html.escape(text[:50])}{"..." if len(text)>50 else ""}'
        if tid:
            return f'分析 #{tid}'
        return html.escape(text[:50]) if text else "分析任务"
    elif task_type == "fetch_price":
        ticker = payload.get("ticker", "") or payload.get("symbol", "")
        return ticker or "股价拉取"
    elif task_type == "fetch_crypto":
        ticker = payload.get("ticker", "") or payload.get("symbol", "") or payload.get("coin", "")
        return ticker or "加密货币拉取"
    elif task_type == "portrait":
        username = payload.get("username", "")
        cnt = payload.get("tweet_count", 0)
        label = payload.get("label", "")
        return f'{username or "?"} ({cnt}条{f" · {label}" if label else ""})'
    elif task_type == "clean":
        target = payload.get("target", "") or payload.get("table", "") or payload.get("action", "")
        return target or "数据清洗"
    # 兜底
    tid = payload.get("tweet_id", "")
    if tid:
        return f'#{tid}'
    txt = payload.get("_text", "") or payload.get("text", "") or payload.get("msg", "")
    if txt:
        return html.escape(txt[:50])
    return "任务"


@register
class PortraitGenerateCard(Card):
    name = "portrait_generate"
    tab = "portraits"
    endpoint = "/api/portrait_generate"
    refresh = 0

    WINDOWS = [
        ("1个月", 30, "近一月"),
        ("3个月", 90, "近三月"),
        ("6个月", 180, "近半年"),
        ("1年", 365, "近一年"),
        ("全量", 9999, "全部历史"),
    ]

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
                      "payload": json.loads(t.payload) if t.payload else {},
                      "created_at": str(t.created_at)[:16] if t.created_at else ""}
                     for t in portrait_tasks]
            s.close()
        except Exception:
            items = []
        return {"tasks": items, "users": _load_users_config()}

    def _render_html(self, data: dict) -> str:
        users = data.get("users", [])
        pending = [t for t in data.get("tasks", []) if t["status"] == "pending"]
        done = [t for t in data.get("tasks", []) if t["status"] == "done"]
        user_opts = "".join(f'<option value="{u}">{u}</option>' for u in users)
        window_btns = "".join(
            f'<button class="btn pg-win-btn" onclick="selectWindow(\'{label}\')" id="pg_win_{label}" style="font-size:10px;padding:3px 8px">{label}({desc})</button>'
            for label, days, desc in self.WINDOWS
        )
        return f'''<div class="card-title">画像生成</div>
<div class="mb-sm"><span class="tag tag-ok">已完成: {len(done)}</span> <span class="tag tag-warn">待处理: {len(pending)}</span></div>

<div class="flex mb-sm" style="gap:6px">
  <select id="pg_user" style="flex:1">{user_opts}</select>
</div>

<div class="mb-sm"><span class="text-secondary" style="font-size:11px">时间窗口</span></div>
<div class="flex mb-sm" style="gap:4px;flex-wrap:wrap" id="pg_windows">{window_btns}</div>

<div class="flex mb-sm" style="gap:6px">
  <input id="pg_from" type="date" style="flex:1;font-size:11px;padding:4px 6px" placeholder="开始日期" />
  <input id="pg_to" type="date" style="flex:1;font-size:11px;padding:4px 6px" placeholder="结束日期" />
</div>

<div class="flex mb-sm" style="gap:6px">
  <input id="pg_label" placeholder="画像标签（可选）" style="flex:1;font-size:11px;padding:4px 6px" />
  <button class="btn btn-primary" onclick="genPortraitAdv()" style="font-size:11px;padding:4px 12px">生成画像</button>
</div>
<input type="hidden" id="pg_window" value="" />
<span id="pg_status" class="text-secondary" style="font-size:10px"></span>

<style>
.pg-win-btn {{ border:0.5px solid var(--border-secondary); }}
.pg-win-btn.selected {{ border-color: var(--text-primary); font-weight:500; }}
</style>'''


def _load_users_config():
    """从 data/users.json 读取监控用户列表。"""
    import json as _j
    from pathlib import Path as _P
    fp = _P("data/users.json")
    if fp.exists():
        return _j.loads(fp.read_text(encoding="utf-8"))
    return ["TJ_Research", "dearbaibabybus"]
