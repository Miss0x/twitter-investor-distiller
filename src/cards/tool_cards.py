"""时间范围控制 + 画像查看 — 工具卡片"""
import json
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
        return {
            "presets": ["最新", "1天", "3天", "7天", "30天", "90天", "180天", "365天", "全部"],
            "users": ["TJ_Research", "dearbaibabybus"],
        }

    def _render_html(self, data: dict) -> str:
        presets = "".join(f'<button class="btn" onclick="setRange(\'{p}\')" style="margin:2px">{p}</button>' for p in data["presets"])
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
</div>
<script>
async function fetchManually(){{
  var u=document.getElementById("fc_user").value;
  var r=document.getElementById("fc_range").value;
  var pages=document.getElementById("fc_pages").value;
  var from=document.getElementById("fc_from").value;
  var to=document.getElementById("fc_to").value;
  var s=document.getElementById("fc_status");
  s.innerText="拉取中...";
  try{{
    var resp=await fetch("/cards/fetch_control/action",{{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{user:u,range:r,pages:pages,from:from,to:to}})}});
    var d=await resp.json();
    s.innerText=d.ok?"完成: +"+d.total+"条":d.error;
    setTimeout(()=>location.reload(),1000);
  }}catch(e){{s.innerText="网络错误";}}
}}
</script>'''


@register
class PortraitCard(Card):
    name = "portrait"
    tab = "pipeline"
    endpoint = "/api/portrait"
    refresh = 300

    def get_data(self, **params) -> dict:
        portraits = {}
        for fp in Path("data/pipeline").glob("*_portrait.md"):
            name = fp.stem.replace("_portrait", "").replace("_", " ")
            portraits[name] = fp.read_text(encoding="utf-8")[:500]
        return {"portraits": portraits}

    def _render_html(self, data: dict) -> str:
        items = "".join(
            f'<div style="margin-bottom:8px"><span style="font-weight:500;font-size:12px">{k}</span><br>'
            f'<span style="font-size:11px;color:var(--text-secondary)">{v[:200]}...</span></div>'
            for k, v in data["portraits"].items()
        ) or '<div class="text-secondary">暂无画像，请先运行流水线</div>'
        return f'<div class="card-title">分析师画像</div>{items}'
