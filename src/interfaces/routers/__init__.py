"""Web API 路由模块（按业务域拆分）。

每个子模块导出 `router: APIRouter`，由 web_api.py 通过 `include_router` 挂载。
"""
