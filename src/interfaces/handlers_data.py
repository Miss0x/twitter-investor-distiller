"""卡片交互处理 — 管理类: 资产代码+画像+用户"""
def _handle_asset_alias(payload: dict) -> dict:
    """处理资产代码库增删改。"""
    from pathlib import Path as _Path
    fp = _Path("data/stock_alias.csv")
    if not fp.exists():
        return {"ok": False, "error": "stock_alias.csv not found"}

    action = payload.get("action", "")
    alias = payload.get("alias", "").strip()
    ticker = payload.get("ticker", "").strip()
    notes = payload.get("notes", "").strip()

    if action == "add":
        if not alias:
            return {"ok": False, "error": "别名不能为空"}
        # 去重检查
        existing = fp.read_text(encoding="utf-8")
        for line in existing.split("\n"):
            if line.startswith("#"): continue
            parts = line.split(",", 2)
            if len(parts) >= 1 and parts[0].strip() == alias:
                return {"ok": False, "error": f"别名 '{alias}' 已存在"}
        with open(fp, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{alias},{ticker if ticker else ''},{notes}\n")
        return {"ok": True}

    elif action == "delete":
        if not alias:
            return {"ok": False, "error": "别名不能为空"}
        lines = fp.read_text(encoding="utf-8").split("\n")
        new_lines = []
        deleted = False
        for line in lines:
            if line.startswith("#") or not line.strip():
                new_lines.append(line)
                continue
            parts = line.split(",", 2)
            if len(parts) >= 1 and parts[0].strip() == alias:
                deleted = True
                continue
            new_lines.append(line)
        if deleted:
            fp.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
            return {"ok": True}
        return {"ok": False, "error": f"别名 '{alias}' 未找到"}

    elif action == "edit":
        if not alias:
            return {"ok": False, "error": "别名不能为空"}
        old_alias = payload.get("old_alias", "").strip()
        target = old_alias or alias
        lines = fp.read_text(encoding="utf-8").split("\n")
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("#") or not line.strip():
                new_lines.append(line)
                continue
            parts = line.split(",", 2)
            if len(parts) >= 1 and parts[0].strip() == target:
                new_lines.append(f"{alias},{ticker if ticker else ''},{notes}")
                found = True
                continue
            new_lines.append(line)
        if found:
            fp.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")
            return {"ok": True}
        return {"ok": False, "error": f"别名 '{target}' 未找到"}

    return {"ok": False, "error": "unknown action"}


def _handle_portrait_generate(payload: dict) -> dict:
    """生成单用户画像，支持时间窗口和日历筛选。"""
    import json as _json
    from pathlib import Path as _Path
    from src.storage.database import db
    from src.storage.models import PipelineTask

    user = payload.get("user", "TJ_Research")
    window = payload.get("window", "全量")
    label = payload.get("label", "").strip()
    from_date = payload.get("from", "").strip()
    to_date = payload.get("to", "").strip()

    # 组合任务用户名：TJ_Research_1个月
    if from_date and to_date:
        composite = f"{user}_{from_date}_{to_date}"
    else:
        composite = f"{user}_{window}"

    payload_dict = {
        "username": composite,
        "action": "generate_portrait",
        "window": window,
    }
    if label:
        payload_dict["label"] = label
    if from_date:
        payload_dict["from"] = from_date
    if to_date:
        payload_dict["to"] = to_date

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
    """添加监控用户，调用 twitterapi.io 校验是否存在。"""
    import json as _json
    from pathlib import Path
    username = payload.get("user", "").strip()
    if not username:
        return {"ok": False, "error": "用户名不能为空"}
    if username.startswith("@"):
        username = username[1:]

    users_fp = Path("data/users.json")
    if not users_fp.exists():
        users_fp.write_text("[]", encoding="utf-8")
    users = _json.loads(users_fp.read_text(encoding="utf-8"))

    if username in users:
        return {"ok": False, "error": f"用户 {username} 已在监控列表中"}

    # 调用 API 校验
    try:
        from src.crawler.twitterapi_fetcher import TwitterAPIFetcher
        f = TwitterAPIFetcher()
        info = f.fetch_user_info(username)
        if not info.get("ok"):
            return {"ok": False, "error": f"API 中未找到用户 @{username}，请确认用户名正确"}
        users.append(username)
        users_fp.write_text(_json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "followers": info.get("followers", "?")}
    except Exception as e:
        return {"ok": False, "error": f"校验失败: {str(e)}"}
