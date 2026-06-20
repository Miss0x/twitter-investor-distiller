"""静态页面路由：/、/dashboard、/timeline/*。

从 web_api.py 抽出，所有路径与原 @app.get 保持完全一致。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.cards.base import TEMPLATE_DIR

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def serve_landing():
    """服务产品首页（Landing Page）。

    展示产品介绍、核心能力和流水线流程，
    引导用户进入控制台。
    """
    landing = TEMPLATE_DIR / "landing.html"
    if landing.exists():
        return HTMLResponse(
            content=landing.read_text(encoding="utf-8"),
        )
    # Fallback：如果 landing.html 不存在，跳转到 dashboard
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """仪表盘主页（需要登录）。未登录重定向到首页。"""
    from src.admin.auth import get_current_user  # noqa: PLC0415
    user = get_current_user(request)
    if user is None:
        return RedirectResponse("/", status_code=302)
    base = TEMPLATE_DIR / "base.html"
    return HTMLResponse(
        content=base.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@router.get("/timeline/{path:path}", response_class=HTMLResponse)
async def serve_timeline(path: str):
    """服务时间线图表 HTML 文件。

    请求格式:
        GET /timeline/some_chart.html

    安全:
        - 路径解析后验证必须在 data/timeline/ 目录内（防目录遍历）
        - 仅允许 .html 文件

    Returns:
        HTMLResponse: 时间线图表的 HTML

    Raises:
        HTTPException(403): 路径不在允许范围内
        HTTPException(404): 文件不存在或不是 .html
    """
    fp = (Path("data/timeline") / path).resolve()
    allowed = Path("data/timeline").resolve()

    # 路径安全检查：防止 ../ 逃逸到上级目录
    if not str(fp).startswith(str(allowed)):
        raise HTTPException(status_code=403, detail="forbidden")

    if fp.exists() and fp.suffix == ".html":
        return HTMLResponse(content=fp.read_text(encoding="utf-8"))

    raise HTTPException(status_code=404, detail="not found")