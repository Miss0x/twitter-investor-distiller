def _handle_role_picker(payload: dict) -> str:
    """处理角色代入选股 LLM 调用。"""
    import json as _json
    from pathlib import Path as _Path
    from src.ai.llm_client import chat

    analyst = payload.get("analyst", "TJ_Research")
    sector = payload.get("sector", "")
    custom = payload.get("custom", "")

    # 加载画像
    candidates = sorted(_Path("data/pipeline").glob(f"{analyst}*portrait.md"))
    if not candidates:
        short = analyst.split("_")[0]
        candidates = sorted(_Path("data/pipeline").glob(f"{short}*portrait.md"))
    portrait = candidates[-1].read_text(encoding="utf-8")[:2000] if candidates else "无画像"

    # 加载准确率
    acc_text = ""
    for afp in _Path("data/accuracy").glob("*_accuracy.json"):
        u = afp.stem.replace("_accuracy", "")
        d = _json.loads(afp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")
        if wr is not None:
            acc_text += f"- {u}: 30日胜率 {wr*100:.0f}%\n"

    # 获取股票池
    sector_map = _json.loads(_Path("data/sector_map.json").read_text(encoding="utf-8"))
    tickers = []
    for k, v in sector_map.items():
        label = f'{v.get("sector","")} / {v.get("industry","")}'
        if label == sector:
            tickers = [t for t, v2 in sector_map.items() if f'{v2.get("sector","")} / {v2.get("industry","")}' == sector]
            break

    # 手动加减
    if custom:
        for part in custom.replace("，", ",").split(","):
            t = part.strip().upper()
            if t.startswith("-"):
                t = t[1:]
                if t in tickers: tickers.remove(t)
            elif t:
                tickers.append(t)

    tickers = sorted(set(tickers))[:15]
    if not tickers:
        return "<div class='text-secondary'>该行业无股票数据</div>"

    # 基本面
    fundamentals = {}
    if _Path("data/fundamental_cache.json").exists():
        fundamentals = _json.loads(_Path("data/fundamental_cache.json").read_text(encoding="utf-8"))

    # 实时价格
    import subprocess as _sp
    prices = {}
    westock_js = str(_Path.home() / ".workbuddy/plugins/marketplaces/cb_teams_marketplace/plugins/finance-data/skills/westock-data/scripts/index.js")
    for t in tickers[:10]:
        try:
            out = _sp.run(["node", westock_js, "quote", f"us{t}"], capture_output=True, text=True, timeout=10,
                          cwd=_Path(westock_js).parent).stdout
            for line in out.split("\n"):
                line = line.strip()
                if not line.startswith("| us"): continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 15:
                    prices[t] = {"price": parts[6], "pe": parts[15], "chg": parts[9]}
        except: pass

    # 建股票表
    rows = ["| Ticker | PE | 价格 | 涨跌 |"]
    rows.append("|--------|-----|------|------|")
    for t in tickers[:12]:
        f = fundamentals.get(t, {})
        p = prices.get(t, {})
        pe = f"{f.get('pe_ratio','?'):.0f}" if f.get('pe_ratio') else "?"
        price = p.get("price", "?")
        chg = p.get("chg", "?")
        rows.append(f"| {t} | {pe} | {price} | {chg} |")

    prompt = f"""[Role] 你是 {analyst} 的投资决策模拟器。
[画像] {portrait}
[准确率] {acc_text}
[任务] 从 {sector} 行业选 3-5 只最符合其理念的标的。理由引用画像维度，仓位总和100%，入场区间+止损。
[股票池]\n{chr(10).join(rows)}
Output: 中文 Markdown。"""

    try:
        return chat(messages=[{"role": "user", "content": prompt}], role="analyzer", max_tokens=4096, temperature=0.5)
    except Exception as e:
        return f"<div class='text-secondary'>LLM 调用失败: {e}</div>"


def _handle_portfolio_analysis(payload: dict) -> str:
    """处理持仓分析 LLM 调用。"""
    import json as _json
    from pathlib import Path as _Path
    from src.ai.llm_client import chat

    text = payload.get("text", "")
    if not text or len(text.strip()) < 10:
        return "<div class='text-secondary'>请输入至少 10 个字符的持仓描述</div>"

    # 加载画像摘要
    portraits = []
    for fp in sorted(_Path("data/pipeline").glob("*全量*portrait.md")):
        username = fp.stem.replace("_全量_portrait", "")
        portraits.append(f"## {username}\n{fp.read_text(encoding='utf-8')[:800]}")

    # 准确率
    acc_text = ""
    for fp in _Path("data/accuracy").glob("*_accuracy.json"):
        u = fp.stem.replace("_accuracy", "")
        d = _json.loads(fp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")
        if wr is not None:
            acc_text += f"- {u}: 30日胜率 {wr*100:.0f}%\n"

    prompt = f"""你是投资顾问。基于分析师画像和准确率，分析我的持仓。
[分析师画像]\n{chr(10).join(portraits)}
[准确率]\n{acc_text}
[我的持仓]\n{text}
每只给出: 1)分析师视角看法(引用画像) 2)仓位/成本/止损建议 3)风险提示。中文Markdown。"""

    try:
        return chat(messages=[{"role": "user", "content": prompt}], role="analyzer", max_tokens=4096, temperature=0.5)
    except Exception as e:
        return f"<div class='text-secondary'>LLM 调用失败: {e}</div>"


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
    action = payload.get("action", "")
    try:
        if action == "seed":
            _sp.run(["python", "scripts/seed_tasks.py"], capture_output=True, text=True, cwd=Path.cwd(), timeout=30)
        elif action == "filter_scan":
            _sp.run(["python", "scripts/run_filter.py"], capture_output=True, text=True, cwd=Path.cwd(), timeout=30)
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
    script = payload.get("script", "")
    if not script or "/" in script or ".." in script:
        return {"ok": False, "error": "invalid script name"}
    try:
        r = _sp.run(["python", f"scripts/{script}"], capture_output=True, text=True, cwd=Path.cwd(), timeout=90)
        output = (r.stdout + r.stderr)[:500]
        return {"ok": r.returncode == 0, "output": output}
    except _sp.TimeoutExpired:
        return {"ok": False, "error": "脚本超时(90s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

