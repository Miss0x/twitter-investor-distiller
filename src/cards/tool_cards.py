"""时间范围控制 + 画像查看 — 工具卡片"""
import json, re
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class FetchControlCard(Card):
    name = "fetch_control"
    tab = "dashboard"
    endpoint = "/api/fetch_control"
    refresh = 0

    def get_data(self, **params) -> dict:
        users = self._load_users()
        return {
            "presets": ["最新", "1天", "3天", "7天", "30天", "90天", "180天", "365天", "全部"],
            "users": users,
        }

    @staticmethod
    def _load_users():
        fp = Path("data/users.json")
        if fp.exists():
            return json.loads(fp.read_text(encoding="utf-8"))
        return ["TJ_Research", "dearbaibabybus"]

    def _render_html(self, data: dict) -> str:
        presets = "".join(f'<button class="btn" onclick="setRange({json.dumps(p)})" style="margin:2px">{p}</button>' for p in data["presets"])
        user_opts = "".join(f'<option>{u}</option>' for u in data["users"])
        return f'''<div class="card-title">手动拉取控制</div>
<div class="grid grid-2 mb-sm" style="gap:8px">
  <div>
    <div class="text-secondary mb-sm">目标用户</div>
    <select id="fc_user">{user_opts}</select>
  </div>
  <div>
    <div class="text-secondary mb-sm">时间范围</div>
    <select id="fc_range">
      <option value="0">仅最新（增量更新）</option>
      <option value="1">1天</option>
      <option value="3">3天</option>
      <option value="7">7天</option>
      <option value="30">30天</option>
      <option value="90">90天</option>
      <option value="180">180天</option>
      <option value="365">365天</option>
      <option value="-1">全部历史</option>
    </select>
  </div>
</div>
<div class="grid grid-2 mb-sm" style="gap:8px">
  <input id="fc_from" type="date" style="font-size:12px;padding:4px 8px" placeholder="开始日期"/>
  <input id="fc_to" type="date" style="font-size:12px;padding:4px 8px" placeholder="结束日期"/>
</div>
<div class="flex" style="gap:8px">
  <input id="fc_pages" type="number" value="10" min="1" max="500" style="width:80px;font-size:12px;padding:4px 8px" title="最大页数"/>
  <button class="btn btn-primary" onclick="fetchManually()">开始拉取</button>
  <span id="fc_status" class="text-secondary" style="font-size:11px"></span>
</div>'''


@register
class PortraitCard(Card):
    name = "portrait"
    tab = "portraits"
    endpoint = "/api/portrait"
    refresh = 300

    def get_data(self, **params) -> dict:
        portraits = []
        for fp in sorted(Path("data/pipeline").glob("*_portrait.md"), reverse=True):
            stem = fp.stem  # e.g. TJ_Research_1个月_portrait
            raw_name = stem.replace("_portrait", "")
            # 解析: TJ_Research_1个月
            m = re.match(r"(.+?)_(1个月|3个月|6个月|1年|全量)", raw_name)
            if m:
                username = m.group(1)
                window = m.group(2)
            elif "_" in raw_name:
                parts = raw_name.split("_", 1)
                username = parts[0]
                window = parts[1] if len(parts) > 1 else ""
            else:
                username = raw_name
                window = "全量"

            content = fp.read_text(encoding="utf-8")
            first_line = content.split("\n", 1)[0].replace("#", "").strip()[:80] if content else ""
            size_kb = round(fp.stat().st_size / 1024, 1)
            # 从元数据头提取推文起止日期 (---\nuser: ...\ndate_range: YYYY-MM-DD ~ YYYY-MM-DD\n---)
            date_range = ""
            tweet_count = ""
            dm = re.search(r"date_range:\s*(\d{4}-\d{2}-\d{2}\s*~\s*\d{4}-\d{2}-\d{2})", content)
            if dm:
                date_range = dm.group(1)
            tm = re.search(r"tweets:\s*(\d+)", content)
            if tm:
                tweet_count = tm.group(1)
            portraits.append({
                "id": stem,
                "username": username,
                "window": window,
                "title": first_line,
                "preview": content[:300],
                "full": content,
                "size_kb": size_kb,
                "date_range": date_range,
                "tweet_count": tweet_count,
                "modified_ts": fp.stat().st_mtime,
            })
        return {"portraits": portraits, "users": list(set(p["username"] for p in portraits))}

    def _render_html(self, data: dict) -> str:
        import time as _tm
        portraits = data["portraits"]
        if not portraits:
            return '<div class="card-title">分析师画像</div><div class="text-secondary">暂无画像。请先运行流水线生成画像。</div>'

        cards = ""
        for p in portraits[:20]:
            mod_time = _tm.strftime("%m-%d %H:%M", _tm.localtime(p["modified_ts"]))
            window_class = "tag-ok" if p["window"] in ("全量", "1年", "6个月") else "tag-warn"
            cards += f'''<div class="portrait-item" style="border:0.5px solid var(--border-tertiary);border-radius:var(--radius-md);padding:8px 10px;margin-bottom:6px;cursor:pointer" onclick="togglePortrait({json.dumps(p["id"])})">
  <div class="flex-between">
    <span><span style="font-weight:500;font-size:12px">{p["username"]}</span>
      <span class="tag {window_class}" style="font-size:10px;margin-left:6px">{p["window"]}</span>
      <span style="font-size:10px;color:var(--text-tertiary);margin-left:8px">{p["size_kb"]}KB</span>
    </span>
    <span style="font-size:10px;color:var(--text-tertiary)">{mod_time}</span>
  </div>
  <div style="font-size:11px;color:var(--text-secondary);margin-top:4px">{p["title"] or "画像"}</div>
  <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px">{'推文: ' + p["tweet_count"] + '条 · ' + p["date_range"] if p["date_range"] else ('推文: ' + p["tweet_count"] + '条' if p["tweet_count"] else '')}</div>
  <div id="portrait-body-{p["id"]}" style="display:none;margin-top:8px;padding:10px;background:var(--bg-secondary);border-radius:var(--radius-md);font-size:12px;max-height:500px;overflow:auto;white-space:pre-wrap;line-height:1.7">{p["full"]}</div>
</div>'''

        return f'''<div class="card-title">分析师画像</div>
<div class="mb-sm"><span class="text-secondary" style="font-size:11px">共 {len(portraits)} 幅 · 点击展开阅读</span></div>
{cards}'''