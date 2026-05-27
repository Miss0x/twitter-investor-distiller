"""卡片交互处理模块 — 执行类。

负责处理 Web Dashboard 中的数据拉取、流水线执行和脚本运行等执行类交互:
    - _handle_fetch_control: 手动拉取推特用户推文
    - _handle_pipeline_action: 流水线任务执行（种子扫描、过滤、分析）
    - _handle_script_run: 运行 scripts/ 目录下的 Python 脚本

这三个函数由 web_api.py 的 /cards/{name}/action 路由通过 import 调用。
"""
def _handle_fetch_control(payload: dict) -> dict:
    """处理手动拉取请求：拉取指定用户的推文。

    业务逻辑:
        1. 解析拉取参数（用户、时间范围、页数）
        2. 计算 since_ts 和 until_ts 时间戳
        3. 调用 TwitterAPIFetcher 执行拉取
        4. 返回拉取结果（新增推文数等）

    支持的时间范围模式:
        - 指定日期: from_date="2024-01-01", to_date="2024-01-31"
        - 最近 N 天: range=7（拉取最近 7 天的推文）
        - range=-1: 拉取全量（since_ts=0）
        - 默认: 从最后一条推文时间戳继续拉取

    Args:
        payload: 前端传来的 JSON，包含:
            - user (str): Twitter 用户名（默认 "TJ_Research"）
            - range (int): 拉取天数（0=默认, -1=全量, >0=最近N天）
            - pages (int): 最大拉取页数（默认 10）
            - from (str): 起始日期 "YYYY-MM-DD"
            - to (str): 结束日期 "YYYY-MM-DD"

    Returns:
        拉取结果字典，包含 total_new、user 等字段
    """
    import time as _time
    from src.crawler.twitterapi_fetcher import TwitterAPIFetcher

    # ── 提取参数 ──
    user = payload.get("user", "TJ_Research")  # 目标用户
    range_days = int(payload.get("range", 0))   # 天数范围（0=默认）
    pages = int(payload.get("pages", 10))       # 最多拉取页数
    from_date = payload.get("from", "")          # 起始日期
    to_date = payload.get("to", "")              # 结束日期

    # ── 计算时间范围 ──
    since_ts, until_ts = 0, 0

    if from_date:
        # 指定日期范围 → 转为秒级时间戳
        since_ts = int(_time.mktime(_time.strptime(from_date, "%Y-%m-%d")))
    if to_date:
        # 结束日期 +1 天（到当天 23:59:59）
        until_ts = int(_time.mktime(_time.strptime(to_date, "%Y-%m-%d"))) + 86400
    elif range_days == -1:
        # 全量拉取
        since_ts = 0
    elif range_days > 0:
        # 最近 N 天
        since_ts = int(_time.time()) - range_days * 86400
    else:
        # 默认模式：从数据库中最后一条推文时间戳续拉
        f = TwitterAPIFetcher()
        since_ts = f.get_last_tweet_ts(user)

    # ── 执行拉取 ──
    f = TwitterAPIFetcher()
    return f.fetch_tweets(user, max_pages=pages, since_ts=since_ts, until_ts=until_ts)


def _handle_pipeline_action(payload: dict) -> dict:
    """处理流水线执行动作：种子创建、过滤扫描、任务执行。

    支持的动作:
        - seed: 运行 scripts/seed_tasks.py，扫描新推文生成待办任务
        - filter_scan: 运行 scripts/run_filter.py，执行推文过滤
        - 其他 (task_type): 调用 PipelineTask 执行器执行指定类型任务（如 analyze、fetch_price）

    Args:
        payload: 前端传来的 JSON，包含:
            - action (str): 动作名（"seed"、"filter_scan" 或其他 task_type）

    Returns:
        执行结果字典，包含 ok 状态和 output/result/error 信息
    """
    import subprocess as _sp
    from pathlib import Path
    action = payload.get("action", "")
    try:
        if action == "seed":
            # ── 种子扫描：扫描新推文并创建任务 ──
            r = _sp.run(["python", "scripts/seed_tasks.py"],
                        capture_output=True, text=True, cwd=Path.cwd(), timeout=30)
            return {"ok": r.returncode == 0,
                    "output": (r.stdout + r.stderr)[:300]} if r.returncode != 0 else {"ok": True}

        elif action == "filter_scan":
            # ── 过滤扫描：对未过滤推文执行投资相关性筛选 ──
            r = _sp.run(["python", "scripts/run_filter.py"],
                        capture_output=True, text=True, cwd=Path.cwd(), timeout=30)
            return {"ok": r.returncode == 0,
                    "output": (r.stdout + r.stderr)[:300]} if r.returncode != 0 else {"ok": True}

        else:
            # ── 执行特定类型 PipelineTask ──
            # action = "analyze" / "fetch_price" / "fetch_crypto" / "portrait"
            from src.pipeline.task_executor import execute_tasks
            result = execute_tasks(action, limit=20)  # 每次最多执行 20 条
            return {"ok": True, "result": str(result)}

        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _handle_script_run(payload: dict) -> dict:
    """运行 scripts/ 目录下的 Python 脚本（用于手动触发辅助脚本）。

    安全限制:
        - 脚本名不能包含路径分隔符（/、\）或上级目录（..），防止路径遍历攻击
        - 超时限制 90 秒，防止脚本失控

    Args:
        payload: 前端传来的 JSON，包含:
            - script (str): 脚本文件名（如 "seed_tasks.py"），必须在 scripts/ 目录下

    Returns:
        执行结果字典，包含 ok 状态和 output/error 信息
    """
    import subprocess as _sp
    from pathlib import Path
    script = payload.get("script", "")

    # ── 安全检查：防止路径遍历攻击 ──
    if not script or "/" in script or "\\" in script or ".." in script:
        return {"ok": False, "error": "invalid script name"}

    try:
        # ── 执行脚本 ──
        r = _sp.run(["python", f"scripts/{script}"],
                    capture_output=True, text=True, cwd=Path.cwd(), timeout=90)
        output = (r.stdout + r.stderr)[:500]  # 截断输出到 500 字符
        return {"ok": r.returncode == 0, "output": output}
    except _sp.TimeoutExpired:
        return {"ok": False, "error": "脚本超时(90s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
