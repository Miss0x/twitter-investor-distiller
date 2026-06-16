"""卡片交互处理模块 — 数据管理类。

负责处理 Web Dashboard 中与数据管理相关的交互请求:
    - _handle_asset_alias: 标的代码（股票/加密货币）映射管理（增删改查）
    - _handle_portrait_generate: 单用户画像生成（支持时间窗口和日历筛选）
    - _handle_user_manage: 监控用户管理（添加/校验新用户）

这些函数由 web_api.py 的 /cards/{name}/action 路由通过 import 调用。
"""
def _handle_asset_alias(payload: dict) -> dict:
    """处理标的代码映射增删改：管理 stock_alias.csv 中的提及名称映射。

    资产别名机制:
        - 如果 LLM 提取的股票名称与 Yahoo Finance ticker 不匹配，可通过别名表映射
        - 如: "NVIDIA" → "NVDA"（LLM 输出的是公司名，需要转为股票代码）
        - 格式: alias,ticker,notes（每行一条映射）

    支持的操作:
        - add: 添加新别名映射（含去重检查）
        - delete: 删除指定别名
        - edit: 修改已有别名的 ticker 或备注
        - skip: 标记跳过（notes 设为 "SKIP"）
        - unskip: 取消跳过标记

    Args:
        payload: 前端传来的 JSON，包含:
            - action (str): 操作类型（"add"/"delete"/"edit"/"skip"/"unskip"）
            - alias (str): 别名名称（如 "NVIDIA"、"比特币"）
            - ticker (str): 映射的目标代码（如 "NVDA"、"BTC-USD"）
            - notes (str): 备注信息
            - old_alias (str): edit 操作时的旧别名（用于重命名）

    Returns:
        操作结果字典，ok=True 表示成功
    """
    from pathlib import Path as _Path
    fp = _Path("data/stock_alias.csv")
    if not fp.exists():
        return {"ok": False, "error": "stock_alias.csv not found"}

    # ── 提取参数 ──
    action = payload.get("action", "")          # 操作类型
    alias = payload.get("alias", "").strip()     # 别名
    ticker = payload.get("ticker", "").strip()   # 目标代码
    notes = payload.get("notes", "").strip()     # 备注

    if action == "add":
        # ── 添加别名映射 ──
        if not alias:
            return {"ok": False, "error": "别名不能为空"}

        # 去重检查：遍历现有行检查是否已存在同名 alias
        existing = fp.read_text(encoding="utf-8")
        for line in existing.split("\n"):
            if line.startswith("#"):
                continue  # 跳过注释行
            parts = line.split(",", 2)  # 最多分 3 部分：alias,ticker,notes
            if len(parts) >= 1 and parts[0].strip() == alias:
                return {"ok": False, "error": f"别名 '{alias}' 已存在"}

        # 追加新行到文件末尾
        with open(fp, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{alias},{ticker if ticker else ''},{notes}\n")
        return {"ok": True}

    elif action == "delete":
        # ── 删除别名映射 ──
        if not alias:
            return {"ok": False, "error": "别名不能为空"}
        lines = fp.read_text(encoding="utf-8").split("\n")
        new_lines = []
        deleted = False
        for line in lines:
            # 保留注释行和空行
            if line.startswith("#") or not line.strip():
                new_lines.append(line)
                continue
            parts = line.split(",", 2)
            if len(parts) >= 1 and parts[0].strip() == alias:
                deleted = True  # 找到匹配行，跳过（不写入）
                continue
            new_lines.append(line)
        if deleted:
            fp.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
            return {"ok": True}
        return {"ok": False, "error": f"别名 '{alias}' 未找到"}

    elif action == "edit":
        # ── 编辑别名映射（修改 ticker/notes，可能同时重命名 alias） ──
        if not alias:
            return {"ok": False, "error": "别名不能为空"}
        old_alias = payload.get("old_alias", "").strip()
        target = old_alias or alias  # 用 old_alias 定位要修改的行
        lines = fp.read_text(encoding="utf-8").split("\n")
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("#") or not line.strip():
                new_lines.append(line)
                continue
            parts = line.split(",", 2)
            if len(parts) >= 1 and parts[0].strip() == target:
                # 替换为新数据
                new_lines.append(f"{alias},{ticker if ticker else ''},{notes}")
                found = True
                continue
            new_lines.append(line)
        if found:
            fp.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
            return {"ok": True}
        return {"ok": False, "error": f"别名 '{target}' 未找到"}

    elif action == "skip":
        # ── 标记跳过（备注设为 SKIP） ──
        return _set_notes(fp, alias, "SKIP")
    elif action == "unskip":
        # ── 取消跳过标记 ──
        return _set_notes(fp, alias, "")

    return {"ok": False, "error": "unknown action"}


def _set_notes(fp, alias: str, notes_val: str) -> dict:
    """修改别名行中的备注字段（内部辅助函数，用于 skip/unskip 操作）。

    业务逻辑:
        - SKIP 操作: 在 existing_notes 前追加 "SKIP|" 前缀，保留原始上下文
        - UNSKIP 操作: 去掉 "SKIP|" 前缀，恢复原始备注

    Args:
        fp: stock_alias.csv 的 Path 对象
        alias: 别名名称
        notes_val: 目标备注值（"SKIP" 表示跳过，"" 表示取消跳过）

    Returns:
        操作结果字典，ok=True 表示成功
    """
    lines = fp.read_text(encoding="utf-8").split("\n")
    new_lines = []
    found = False
    for line in lines:
        # 注释行和空行保留不动
        if line.startswith("#") or not line.strip():
            new_lines.append(line)
            continue
        parts = line.split(",", 2)  # alias,ticker,notes
        if len(parts) >= 1 and parts[0].strip() == alias:
            found = True
            ticker = parts[1].strip() if len(parts) >= 2 else ""
            old_notes = parts[2].strip() if len(parts) >= 3 else ""

            if notes_val == "SKIP":
                # 标记跳过：保留原始备注上下文 "SKIP|原备注"
                new_notes = "SKIP|" + old_notes if old_notes else "SKIP"
            else:
                # 取消跳过：去掉 "SKIP|" 前缀
                new_notes = old_notes.replace("SKIP|", "", 1) if old_notes.startswith("SKIP|") else ""

            new_lines.append(f"{alias},{ticker},{new_notes}")
            continue
        new_lines.append(line)

    if found:
        fp.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
        return {"ok": True}
    return {"ok": False, "error": f"别名 '{alias}' 未找到"}


def _handle_portrait_generate(payload: dict) -> dict:
    """生成单用户投资画像：创建 portrait 类型的 PipelineTask。

    业务逻辑:
        1. 组合任务标识（用户名_时间窗口 或 用户名_日期范围）
        2. 构建 payload 字典（包含窗口、标签、日期范围等）
        3. 写入 PipelineTask 到数据库（status=pending）
        4. 后续由流水线执行器调用 AI 生成画像

    支持的模式:
        - 时间窗口: "1个月"、"3个月"、"6个月"、"1年"、"全量"
        - 自定义日期: from_date="2024-01-01", to_date="2024-06-30"

    Args:
        payload: 前端传来的 JSON，包含:
            - user (str): 分析师用户名（默认 "TJ_Research"）
            - window (str): 时间窗口（"全量"/"1个月"等，默认 "全量"）
            - label (str): 自定义标签
            - from (str): 起始日期 "YYYY-MM-DD"
            - to (str): 结束日期 "YYYY-MM-DD"

    Returns:
        操作结果字典，ok=True 时包含 task_id
    """
    import json as _json
    from src.storage.database import db
    from src.storage.models import PipelineTask

    # ── 提取参数 ──
    user = payload.get("user", "TJ_Research")
    window = payload.get("window", "全量")
    label = payload.get("label", "").strip()
    from_date = payload.get("from", "").strip()
    to_date = payload.get("to", "").strip()

    # ── 组合任务标识 ──
    if from_date and to_date:
        # 自定义日期范围: TJ_Research_2024-01-01_2024-06-30
        composite = f"{user}_{from_date}_{to_date}"
    else:
        # 预设时间窗口: TJ_Research_1个月
        composite = f"{user}_{window}"

    # ── 构建任务 payload ──
    payload_dict = {
        "username": composite,
        "action": "generate_portrait",  # 执行器根据此字段调用画像生成逻辑
        "window": window,
    }
    if label:
        payload_dict["label"] = label
    if from_date:
        payload_dict["from"] = from_date
    if to_date:
        payload_dict["to"] = to_date

    # ── 创建 PipelineTask 写入数据库 ──
    try:
        db.init_db()
        s = db.get_session()
        task = PipelineTask(
            task_type="portrait",
            status="pending",
            payload=_json.dumps(payload_dict, ensure_ascii=False),
        )
        s.add(task)
        s.commit()
        s.close()
        return {"ok": True, "task_id": task.id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _handle_user_manage(payload: dict) -> dict:
    """添加监控用户：通过 TwitterAPI 校验用户是否存在后加入监控列表。

    业务逻辑:
        1. 清理用户名（去掉 @ 前缀）
        2. 检查是否已在监控列表中（data/users.json）
        3. 通过 TwitterAPIFetcher.fetch_user_info() 校验用户是否存在
        4. 校验通过后追加到 users.json

    Args:
        payload: 前端传来的 JSON，包含:
            - user (str): Twitter 用户名（可带 @ 前缀）

    Returns:
        操作结果字典，ok=True 时包含 followers 粉丝数
    """
    import json as _json
    from pathlib import Path
    username = payload.get("user", "").strip()
    if not username:
        return {"ok": False, "error": "用户名不能为空"}

    # 去掉 @ 前缀（如 "@TJ_Research" → "TJ_Research"）
    if username.startswith("@"):
        username = username[1:]

    # ── 检查 users.json 是否存在 ──
    users_fp = Path("data/users.json")
    if not users_fp.exists():
        users_fp.write_text("[]", encoding="utf-8")  # 不存在则创建空列表
    users = _json.loads(users_fp.read_text(encoding="utf-8"))

    # ── 去重检查 ──
    if username in users:
        return {"ok": False, "error": f"用户 {username} 已在监控列表中"}

    # ── 通过 API 校验用户是否存在 ──
    try:
        from src.crawler.twitterapi_fetcher import TwitterAPIFetcher
        f = TwitterAPIFetcher()
        info = f.fetch_user_info(username)  # 调用 TwitterAPI.io 获取用户信息
        if not info.get("ok"):
            return {"ok": False, "error": f"API 中未找到用户 @{username}，请确认用户名正确"}

        # 校验通过，添加到监控列表
        users.append(username)
        users_fp.write_text(_json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "followers": info.get("followers", "?")}
    except Exception as e:
        return {"ok": False, "error": f"校验失败: {str(e)}"}
