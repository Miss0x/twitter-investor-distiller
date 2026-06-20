"""
流水线执行面板卡片
====================

只有一个卡片：
  1. PipelineExecuteCard — 流水线任务管理面板
     - 展示所有流水线任务（filter/analyze/fetch_price/fetch_crypto/portrait/clean）
     - 支持按类型分组查看、全选/取消、执行选中任务、重试/跳过失败任务
     - 内嵌"数据清洗"tab 用于管理资产代码别名映射
     - refresh=15s 高频刷新以实时追踪任务进度

PortraitGenerateCard 已移到 portrait_generate.py。
"""
import html
import json
from src.cards.base import Card
from src.cards import register


@register
class PipelineExecuteCard(Card):
    """
    流水线执行面板卡片。

    属性:
        name="pipeline_execute"  — 唯一标识
        tab="pipeline"           — 属于流水线标签页
        endpoint="/api/pipeline_execute" — API 路由
        refresh=15               — 每 15 秒自动刷新（流水线状态频繁变化）
    """

    name = "pipeline_execute"
    tab = "pipeline"
    endpoint = "/api/pipeline_execute"
    refresh = 15

    def get_data(self, **params) -> dict:
        """
        从 PipelineTask 表和 data/stock_alias.csv 获取数据。

        返回结构:
            {
                "groups": {            # 按 task_type 分组的任务列表
                    "filter": [{id, task_type, status, payload, error_msg, created_at}, ...],
                    "analyze": [...],
                    "fetch_price": [...],
                    "fetch_crypto": [...],
                    "portrait": [...],
                    "clean": [...]     # clean 类型用于数据清洗
                },
                "running": bool,       # 是否有流水线正在运行
                "progress": dict,      # 当前进度 {msg, done, total}
                "type_counts": dict,   # 各类型任务总数 {filter: N, analyze: M, ...}
                "types": [...],        # 所有类型名列表
                "alias_stats": {       # 资产别名校准统计
                    "confirmed": int,  # 已确认映射数
                    "pending": int,    # 待人工判断数
                    "skipped": int,    # 已跳过数
                    "total": int       # 总数
                }
            }
        """
        try:
            from src.storage.database import db
            from src.storage.models import PipelineTask
            db.init_db()
            s = db.get_session()
            try:
                tasks = s.query(PipelineTask).order_by(PipelineTask.id.desc()).limit(200).all()
                grouped = {}
                for t in tasks:
                    p = json.loads(t.payload) if t.payload else {}
                    item = {"id": t.id, "task_type": t.task_type, "status": t.status,
                            "payload": p, "error_msg": t.error_msg,
                            "created_at": str(t.created_at)[:16] if t.created_at else ""}
                    grouped.setdefault(t.task_type, []).append(item)
            finally:
                s.close()
            from src.pipeline.task_executor import is_running, get_progress
            from collections import Counter
            type_counts = Counter(t.task_type for t in tasks)

            # ── 数据清洗：加载别名统计 + 完整别名列表示例 ══
            alias_stats = {"confirmed": 0, "pending": 0, "skipped": 0, "total": 0}
            aliases_list = []
            try:
                from src.storage.alias_repository import AliasRepository
                for a in AliasRepository.get_all():
                    alias_stats["total"] += 1
                    if a.ticker:
                        alias_stats["confirmed"] += 1
                    elif a.notes.startswith("SKIP"):
                        alias_stats["skipped"] += 1
                    else:
                        alias_stats["pending"] += 1
                    if a.alias:
                        aliases_list.append({"alias": a.alias, "ticker": a.ticker, "type": a.notes})
            except Exception:
                pass

            return {
                "groups": grouped,
                "running": is_running(),
                "progress": get_progress(),
                "type_counts": dict(type_counts),
                "types": ["filter", "analyze", "fetch_price", "fetch_crypto", "portrait", "clean"],
                "alias_stats": alias_stats,
                "aliases_list": aliases_list,
            }
        except Exception:
            return {"groups": {}, "running": False, "progress": {}, "types": [], "alias_stats": [], "aliases_list": []}

    def _render_html(self, data: dict) -> str:
        """
        生成流水线执行面板的完整 HTML。

        HTML 结构概览:
            1. 标题栏 — "流水线执行" + 运行状态指示灯
            2. 统计标签行 — 各类型任务数量 badge
            3. 主 tab 按钮组 — 切换 filter/analyze/portrait/clean 视图
               (fetch_price/fetch_crypto 嵌套在 analyze 下作为前置子功能)
            4. 操作按钮行 — 扫描新内容按钮（seedTasksPE）
            5. 各类型任务容器 — 每个 tab 对应一个 pe-type-{t} 容器:
               - 待办表格（含复选框、ID、详情列） + 全选/取消/执行选中按钮
               - 失败表格（含重试/跳过按钮）
               - clean 类型特殊处理: 内嵌标的代码映射完整管理界面
        """
        groups = data.get("groups", {})
        running = data.get("running", False)
        progress = data.get("progress", {})
        tc = data.get("type_counts", {})
        type_names = {
            "filter": "筛选推文", "analyze": "分析观点",
            "fetch_price": "补全行情", "fetch_crypto": "补全加密行情",
            "portrait": "生成画像", "clean": "校准标的",
        }
        # 主 tab，fetch_price/fetch_crypto 为推文分析的前置子功能
        main_types = ["filter", "analyze", "portrait", "clean"]
        sub_of = {"fetch_price": "analyze", "fetch_crypto": "analyze"}

        # ── 批量查推文文本，注入到 filter / analyze payload 中 ──
        _enrich_tweet_texts(groups)

        # 主 tab 按钮（fetch_price/fetch_crypto 嵌套在推文分析下）
        all_ts = ["filter", "analyze", "fetch_price", "fetch_crypto", "portrait", "clean"]

        type_tabs = "".join(
            f'<button class="tab pe-tab" data-action="load-type-pe" data-type="{t}" id="tab-{t}">{type_names[t]}</button>'
            for t in main_types
        )
        status_bar = f'执行中: {progress.get("msg","")} ({progress.get("done",0)}/{progress.get("total",0)})' if running else "空闲"
        type_tags = "".join(
            f'<span class="tag tag-ok">{type_names.get(t,t)}: {tc.get(t,0)}</span>'
            for t in all_ts if tc.get(t, 0) > 0
        )

        containers = ""
        for t in all_ts:
            items = groups.get(t, [])
            if t == "clean":
                # ── 校准标的：从 data（get_data 已解析）读取别名映射 ──
                aliases_list = data.get("aliases_list", [])
                confirmed = [a for a in aliases_list if a["ticker"]]
                pending = [a for a in aliases_list if not a["ticker"] and not a.get("type","").startswith("SKIP")]
                skipped = [a for a in aliases_list if not a["ticker"] and a.get("type","").startswith("SKIP")]

                confirmed_rows = "".join(
                    f'<tr><td style="font-size:11px">{a["alias"]}</td><td style="font-weight:500">{a["ticker"]}</td><td style="font-size:11px;color:var(--text-secondary)">{a.get("type","")}</td><td style="text-align:right"><button class="btn" style="font-size:10px;padding:1px 6px" data-action="edit-alias" data-alias="{html.escape(a["alias"])}" data-ticker="{html.escape(a["ticker"])}" data-notes="{html.escape(a.get("type",""))}">编辑</button> <button class="btn btn-danger" style="font-size:10px;padding:1px 6px" data-action="delete-alias" data-alias="{html.escape(a["alias"])}">删除</button></td></tr>'
                    for a in confirmed[:50]
                ) if confirmed else '<tr><td colspan="4" class="text-secondary">暂无已确认映射</td></tr>'

                pending_rows = "".join(
                    f'<tr style="background:rgba(239,159,39,0.05)"><td style="font-size:11px;font-weight:500">{a["alias"]}</td><td style="font-size:11px;color:var(--text-secondary)">{a.get("type","")}</td><td style="text-align:right"><button class="btn" style="font-size:10px;padding:1px 6px" data-action="fill-alias" data-alias="{html.escape(a["alias"])}" data-notes="{html.escape(a.get("type",""))}">填写代码</button> <button class="btn" style="font-size:10px;padding:1px 6px;border-color:var(--text-tertiary);color:var(--text-tertiary)" data-action="skip-alias" data-alias="{html.escape(a["alias"])}">跳过</button> <button class="btn btn-danger" style="font-size:10px;padding:1px 6px" data-action="delete-alias" data-alias="{html.escape(a["alias"])}">删除</button></td></tr>'
                    for a in pending[:30]
                ) if pending else '<tr><td colspan="4" class="text-secondary" style="color:var(--text-success)">全部确认完毕</td></tr>'

                skipped_rows = "".join(
                    f'<tr style="opacity:0.5"><td style="font-size:11px">{a["alias"]}</td><td style="font-size:11px;color:var(--text-secondary)">{a.get("type","").replace("SKIP|","",1)}</td><td style="text-align:right"><button class="btn" style="font-size:10px;padding:1px 6px" data-action="unskip-alias" data-alias="{html.escape(a["alias"])}">恢复</button></td></tr>'
                    for a in skipped[:30]
                )

                containers += f'''<div id="pe-type-clean" class="pe-container" style="display:none">
<div class="flex-between mb-sm"><span style="font-size:12px;font-weight:500">标的代码映射</span><button class="btn" data-action="run-clean" data-card="pipeline_execute" style="font-size:11px">应用映射修正</button></div>
<div class="mb-sm"><span id="pipeline_execute-clean_status" class="text-secondary" style="font-size:11px"></span></div>
<div class="grid grid-4 mb-sm">
  <div class="metric"><div class="metric-label">总映射</div><div class="metric-value">{len(aliases_list)}</div></div>
  <div class="metric"><div class="metric-label">已确认</div><div class="metric-value" style="color:var(--text-success)">{len(confirmed)}</div></div>
  <div class="metric"><div class="metric-label">待判断</div><div class="metric-value" style="color:var(--text-warning)">{len(pending)}</div></div>
  <div class="metric"><div class="metric-label">已跳过</div><div class="metric-value" style="color:var(--text-tertiary)">{len(skipped)}</div></div>
</div>
<div class="flex mb-sm" style="gap:4px;flex-wrap:wrap">
  <input id="pipeline_execute-aa_alias" placeholder="提及名称" style="flex:1;min-width:80px;font-size:11px;padding:4px 6px" />
  <input id="pipeline_execute-aa_ticker" placeholder="标的代码" style="flex:1;min-width:60px;font-size:11px;padding:4px 6px" />
  <input id="pipeline_execute-aa_notes" placeholder="备注" style="flex:1;min-width:60px;font-size:11px;padding:4px 6px" />
  <button class="btn btn-primary" data-action="add-alias" data-card="pipeline_execute" style="font-size:11px;padding:4px 10px" id="pipeline_execute-btn_aa_submit">添加</button>
</div>
<input type="hidden" id="pipeline_execute-aa_old_alias" value="" />
<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-primary)">已确认映射 ({len(confirmed)}条)</span></div>
<table class="data"><tr><th>提及名称</th><th>标的代码</th><th>备注</th><th style="text-align:right">操作</th></tr>{confirmed_rows}</table>
<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-warning)">待人工判断 ({len(pending)}条)</span></div>
<table class="data"><tr><th>提及名称</th><th>系统标注</th><th style="text-align:right">操作</th></tr>{pending_rows}</table>
{skipped_rows and f'<div class="mt-md mb-sm"><span style="font-size:12px;font-weight:500;color:var(--text-tertiary)">已跳过 ({len(skipped)}条)</span></div><table class="data"><tr><th>提及名称</th><th>系统标注</th><th style="text-align:right">操作</th></tr>' + skipped_rows + '</table>'}
<div class="text-secondary mt-sm" style="font-size:10px">提示：点"填写代码"自动回填表单，输入标的代码后提交即可移入已确认列表。跳过则暂不处理。</div>
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
                f'<td><button class="btn" style="font-size:10px;padding:2px 6px" data-action="retry-task" data-id="{f["id"]}">重试</button> '
                f'<button class="btn" style="font-size:10px;padding:2px 6px" data-action="skip-task" data-id="{f["id"]}">跳过</button></td></tr>'
                for f in failed[:10]
            ) if failed else ''

            # 子 tab 视觉标记
            section_title = type_names.get(t, t)
            if t in sub_of:
                section_title = f'└ 前置数据: {section_title}'

            containers += f'''<div id="pe-type-{t}" class="pe-container" style="display:none">
<div class="flex-between mb-sm"><span class="text-secondary" style="font-size:11px">
{section_title} · 待办 {len(pending)} | 完成 {len(done)} | 失败 {len(failed)}</span>
<span><button class="btn" style="font-size:10px;padding:2px 6px" data-action="select-all-pe" data-type="{t}">全选</button>
<button class="btn" style="font-size:10px;padding:2px 6px" data-action="clear-all-pe" data-type="{t}">取消</button>
<button class="btn" style="font-size:10px;padding:2px 6px" data-action="exec-pipeline" data-type="{t}">▶ 执行选中</button></span></div>
<table class="data"><tr><th style="width:24px"></th><th>ID</th><th>详情</th></tr>{pending_rows}</table>
{f'<div class="mt-sm"><span class="text-secondary" style="font-size:11px">失败 ({len(failed)})</span><table class="data">{failed_rows}</table></div>' if failed else ''}
</div>'''

        return f'''<div class="card-title">处理队列</div>
<div class="mb-sm" style="font-size:11px;color:var(--text-secondary);line-height:1.6">
  <span class="tag tag-ok">1 采集内容</span>
  <span class="text-secondary">→</span>
  <span class="tag tag-warn">2 扫描新内容</span>
  <span class="text-secondary">→</span>
  <span class="tag tag-ok">3 运行分析流程</span>
</div>
<div class="flex-between mb-sm"><div class="flex"><div class="status-dot {"ok" if running else ""}"></div><span style="font-size:12px">{status_bar}</span></div></div>
<div class="mb-sm" style="display:flex;gap:4px;flex-wrap:wrap">{type_tags}</div>
<div class="mb-sm" style="display:flex;gap:4px;flex-wrap:wrap">{type_tabs}</div>
<div style="display:flex;gap:6px;margin-bottom:8px">
  <button class="btn" data-action="seed-tasks" data-card="pipeline_execute" style="font-size:11px">扫描新内容</button>
  <span id="pe-msg" class="text-secondary" style="font-size:11px"></span>
</div>
{containers}
</div>'''


# ────────────────────────────────────────────────────────────
# 辅助函数
# ────────────────────────────────────────────────────────────

def _enrich_tweet_texts(groups: dict) -> None:
    """批量查询推文文本并注入到 filter / analyze 任务的 payload 中。

    从 data/twitter_data.db 的 tweets 表按 tweet_id 批量查询正文和作者，
    将结果注入到 payload["_text"] 和 payload["_user"] 字段，
    供 _format_label() 和渲染时使用。

    采用分批查询（每批 900 条），使用只读 WAL 模式避免锁冲突。
    查询失败时仅记录 warning 日志，不中断流程。
    """
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

    # 批量 DB 查询（使用绝对路径和 WAL 模式，避免路径/锁问题）
    try:
        from src.storage.database import db
        from src.storage.models import Tweet
        s = db.get_session()
        try:
            tweet_ids_list = list(tweet_ids)
            text_map = {}
            for start in range(0, len(tweet_ids_list), 900):
                chunk = tweet_ids_list[start:start+900]
                for tw in s.query(Tweet).filter(Tweet.id.in_(chunk)).all():
                    text_map[tw.id] = {"text": tw.text or "", "user_id": str(tw.user_id)}
        finally:
            s.close()
    except Exception as e:
        import logging
        logging.getLogger("pipeline_execute").warning(f"_enrich_tweet_texts DB 查询失败: {e}")
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
    """将任务 payload 转换为可读的中文描述文本。

    根据 task_type 采用不同的格式化策略:
      - filter:   优先展示注入的推文文本（@user + 正文预览），否则显示 action 名 + tweet_id
      - analyze:  展示 tweet_id + 推文正文预览
      - fetch_price:  展示 ticker 代码
      - fetch_crypto: 展示加密货币 ticker
      - portrait: 展示用户名 + 推文数量 + 标签
      - clean:    展示数据清洗目标

    参数:
        task_type: 任务类型字符串（filter|analyze|fetch_price|fetch_crypto|portrait|clean）
        payload:   任务 payload 字典，可能包含 _text, _user, tweet_id, ticker, username 等

    返回:
        str: 格式化的中文描述，最长约 60 字符
    """
    # filter: 优先展示注入的推文文本
    if task_type == "filter":
        txt = payload.get("_text", "")
        if txt:
            prefix = f'@{payload.get("_user","")} ' if payload.get("_user") else ""
            return f'{prefix}{html.escape(txt[:50])}{"..." if len(txt)>50 else ""}'
        # 没有文本则尝试显示 tweet_id
        tid = payload.get("tweet_id", "")
        action = payload.get("action", "")
        action_labels = {
            "filter_single": "单条过滤",
            "filter_latest": "最新推文过滤",
            "filter_media": "媒体过滤",
            "filter_replies": "回复过滤",
        }
        label = action_labels.get(action, action or "推文过滤")
        if tid:
            return f"#{tid} {label}"
        return label
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
        return ticker or "补全行情"
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

