"""卡片交互处理 — 执行类: 拉取控制+流水线+脚本"""
def _handle_fetch_control(payload: dict) -> dict:
    """处理手动拉取请求。"""
    import time as _time
    from src.crawler.twitterapi_fetcher import TwitterAPIFetcher

    user = payload.get("user", "TJ_Research")
    range_days = int(payload.get("range", 0))
    pages = int(payload.get("pages", 10))
    from_date = payload.get("from", "")
    to_date = payload.get("to", "")

    since_ts, until_ts = 0, 0

    if from_date:
        since_ts = int(_time.mktime(_time.strptime(from_date, "%Y-%m-%d")))
    if to_date:
        until_ts = int(_time.mktime(_time.strptime(to_date, "%Y-%m-%d"))) + 86400
    elif range_days == -1:
        since_ts = 0
    elif range_days > 0:
        since_ts = int(_time.time()) - range_days * 86400
    else:
        f = TwitterAPIFetcher()
        since_ts = f.get_last_tweet_ts(user)

    f = TwitterAPIFetcher()
    return f.fetch_tweets(user, max_pages=pages, since_ts=since_ts, until_ts=until_ts)


def _handle_pipeline_action(payload: dict) -> dict:
    """处理流水线执行动作。"""
    import subprocess as _sp
    from pathlib import Path
    action = payload.get("action", "")
    try:
        if action == "seed":
            r = _sp.run(["python", "scripts/seed_tasks.py"], capture_output=True, text=True, cwd=Path.cwd(), timeout=30)
            return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr)[:300]} if r.returncode != 0 else {"ok": True}
        elif action == "filter_scan":
            r = _sp.run(["python", "scripts/run_filter.py"], capture_output=True, text=True, cwd=Path.cwd(), timeout=30)
            return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr)[:300]} if r.returncode != 0 else {"ok": True}
        else:
            # 执行特定类型任务
            from src.pipeline.task_executor import execute_tasks
            result = execute_tasks(action, limit=20)
            return {"ok": True, "result": str(result)}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _handle_script_run(payload: dict) -> dict:
    """运行 scripts/ 下的脚本。"""
    import subprocess as _sp
    from pathlib import Path
    script = payload.get("script", "")
    if not script or "/" in script or "\\" in script or ".." in script:
        return {"ok": False, "error": "invalid script name"}
    try:
        r = _sp.run(["python", f"scripts/{script}"], capture_output=True, text=True, cwd=Path.cwd(), timeout=90)
        output = (r.stdout + r.stderr)[:500]
        return {"ok": r.returncode == 0, "output": output}
    except _sp.TimeoutExpired:
        return {"ok": False, "error": "脚本超时(90s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
