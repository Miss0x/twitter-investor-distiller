"""
工具卡片组（Tool Cards）
========================

包含两个工具型卡片：
  1. FetchControlCard — 手动推文拉取控制面板（选择用户 + 时间范围）
  2. PortraitCard     — 分析师画像浏览面板（列出已生成的画像文件）
"""
import json, re, html
from pathlib import Path
from src.cards.base import Card
from src.cards import register


@register
class FetchControlCard(Card):
    """
    手动拉取控制卡片。

    前端交互面板，用于手动触发特定用户在特定时间范围的推文拉取。

    属性:
        name="fetch_control"       — 唯一标识
        tab="dashboard"            — 属于主仪表盘标签页
        endpoint="/api/fetch_control" — API 路由
        refresh=0                  — 不自动刷新（手动操作卡片）
        template="fetch_control.html" — Jinja2 模板

    get_data() 返回结构:
        {
            "presets": ["最新","1天","3天","7天","30天","90天","180天","365天","全部"],
            "users": ["TJ_Research", "dearbaibabybus", ...]  # 监控用户列表
        }
    """
    name = "fetch_control"
    def get_data(self, **params) -> dict:
        users = self._load_users()
        # 结构化 presets：value 对应后端 range_days 参数
        return {
            "presets": [
                {"value": 0, "label": "仅最新（增量更新）"},
                {"value": 1, "label": "1天"},
                {"value": 3, "label": "3天"},
                {"value": 7, "label": "7天"},
                {"value": 30, "label": "30天"},
                {"value": 90, "label": "90天"},
                {"value": 180, "label": "180天"},
                {"value": 365, "label": "365天"},
                {"value": -1, "label": "全部历史"},
            ],
            "users": users,
        }

    @staticmethod
    def _load_users():
        """
        从 data/users.json 加载监控用户列表。

        返回:
            list[str]: 用户名列表，文件不存在时返回默认列表
        """
        fp = Path("data/users.json")
        if fp.exists():
            return json.loads(fp.read_text(encoding="utf-8"))
        return ["TJ_Research", "dearbaibabybus"]


@register
class PortraitCard(Card):
    """
    分析师画像浏览卡片。

    列出 data/pipeline/ 下所有 *_portrait.md 文件，
    按分析师和窗口分组展示，支持点击展开阅读完整内容。

    属性:
        name="portrait"           — 唯一标识
        tab="portraits"           — 属于画像标签页
        endpoint="/api/portrait"  — API 路由
        refresh=300               — 每 5 分钟自动刷新

    get_data() 返回结构:
        {
            "portraits": [
                {
                    "id": "TJ_Research_1个月_portrait",  # 文件标识
                    "username": "TJ_Research",            # 分析师用户名
                    "window": "1个月",                     # 时间窗口
                    "title": "...",                       # Markdown 首行标题
                    "preview": "...",                     # 前300字符预览
                    "full": "...",                        # 完整内容
                    "size_kb": 12.5,                      # 文件大小(KB)
                    "date_range": "2025-01-01 ~ ...",     # 推文日期范围
                    "tweet_count": "1500",                # 推文总数
                    "modified_ts": 1700000000.0           # 文件修改时间戳
                },
                ...
            ],
            "users": ["TJ_Research", ...]   # 所有分析师用户名
        }
    """
    name = "portrait"
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
        """
        生成画像浏览界面的 HTML。

        HTML 结构概览:
            1. 标题栏 — "分析师画像" + 总数统计
            2. 画像卡片列表（portrait-item）:
               - 每张卡片显示: 用户名 + 窗口标签 + 文件大小 + 修改时间
               - 画像标题（Markdown 首行）
               - 推文数量 + 日期范围
               - 隐藏的完整内容 div（点击展开/收起，max-height 500px 可滚动）
        """
        import time as _tm
        portraits = data["portraits"]
        if not portraits:
            return '<div class="card-title">分析师画像</div><div class="text-secondary">暂无画像。请先运行流水线生成画像。</div>'

        cards = ""
        for p in portraits[:20]:
            mod_time = _tm.strftime("%m-%d %H:%M", _tm.localtime(p["modified_ts"]))
            window_class = "tag-ok" if p["window"] in ("全量", "1年", "6个月") else "tag-warn"
            pid_safe = html.escape(str(p["id"]), quote=True)
            username_safe = html.escape(str(p["username"]))
            window_safe = html.escape(str(p["window"]))
            title_safe = html.escape(str(p["title"] or "画像"))
            full_safe = html.escape(str(p["full"]))
            cards += f'''<div class="portrait-item" style="border:0.5px solid var(--border-tertiary);border-radius:var(--radius-md);padding:8px 10px;margin-bottom:6px;cursor:pointer" data-action="toggle-portrait" data-id="{pid_safe}">
  <div class="flex-between">
    <span><span style="font-weight:500;font-size:12px">{username_safe}</span>
      <span class="tag {window_class}" style="font-size:10px;margin-left:6px">{window_safe}</span>
      <span style="font-size:10px;color:var(--text-tertiary);margin-left:8px">{p["size_kb"]}KB</span>
    </span>
    <span style="font-size:10px;color:var(--text-tertiary)">{mod_time}</span>
  </div>
  <div style="font-size:11px;color:var(--text-secondary);margin-top:4px">{title_safe}</div>
  <div style="font-size:10px;color:var(--text-tertiary);margin-top:2px">{'推文: ' + str(p["tweet_count"]) + '条 · ' + p["date_range"] if p["date_range"] else ('推文: ' + str(p["tweet_count"]) + '条' if p["tweet_count"] else '')}</div>
  <div id="portrait-body-{p["id"]}" style="display:none;margin-top:8px;padding:10px;background:var(--bg-secondary);border-radius:var(--radius-md);font-size:12px;max-height:500px;overflow:auto;white-space:pre-wrap;line-height:1.7">{full_safe}</div>
</div>'''

        return f'''<div class="card-title">分析师画像</div>
<div class="mb-sm"><span class="text-secondary" style="font-size:11px">共 {len(portraits)} 幅 · 点击展开阅读</span></div>
{cards}'''