"""卡片交互处理模块 — 洞察类。

负责处理 Web Dashboard 中与 AI 分析洞察相关的交互请求:
    - _handle_role_picker: 角色代入选股（LLM 模拟特定分析师的选股决策）
    - _handle_portfolio_analysis: 持仓分析顾问（LLM 分析用户持仓组合）

这两个函数由 web_api.py 的 /cards/{name}/action 路由通过 import 调用。
"""
def _handle_role_picker(payload: dict) -> str:
    """处理角色代入选股 LLM 调用。

    业务逻辑:
        1. 加载目标分析师的投资画像（portrait.md）
        2. 加载各分析师的 30 日胜率数据
        3. 根据所选行业获取股票池（sector_map.json）
        4. 支持手动加减标的
        5. 通过 westock-data 获取实时价格
        6. 构建 Prompt 调用 LLM 进行选股决策

    Args:
        payload: 前端传来的 JSON，包含:
            - analyst (str): 分析师用户名（如 "TJ_Research"）
            - sector (str): 行业名称（如 "科技 / 软件"）
            - custom (str): 手动加减标的（逗号分隔，前缀 - 表示剔除）

    Returns:
        LLM 生成的选股分析 HTML/Markdown 内容，或错误提示
    """
    import json as _json
    from pathlib import Path as _Path
    from src.ai.llm_client import chat

    # ── 提取参数 ──
    analyst = payload.get("analyst", "TJ_Research")  # 默认 TJ_Research
    sector = payload.get("sector", "")                # 行业筛选条件
    custom = payload.get("custom", "")                # 用户自定义股票

    # ── 加载分析师画像 ──
    # 画像存储在 data/pipeline/<分析师>_*_portrait.md
    candidates = sorted(_Path("data/pipeline").glob(f"{analyst}*portrait.md"))
    if not candidates:
        # 尝试用用户名简称匹配
        short = analyst.split("_")[0]
        candidates = sorted(_Path("data/pipeline").glob(f"{short}*portrait.md"))
    portrait = candidates[-1].read_text(encoding="utf-8")[:2000] if candidates else "无画像"

    # ── 加载各分析师的准确率数据 ──
    # accuracy 数据存储在 data/accuracy/<用户>_accuracy.json
    acc_text = ""
    for afp in _Path("data/accuracy").glob("*_accuracy.json"):
        u = afp.stem.replace("_accuracy", "")  # 提取用户名
        d = _json.loads(afp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")  # 30日胜率
        if wr is not None:
            acc_text += f"- {u}: 30日胜率 {wr*100:.0f}%\n"

    # ── 获取行业股票池 ──
    # sector_map.json: {ticker: {sector, industry, ...}}
    sector_map = _json.loads(_Path("data/sector_map.json").read_text(encoding="utf-8"))
    tickers = []
    for k, v in sector_map.items():
        label = f'{v.get("sector","")} / {v.get("industry","")}'
        if label == sector:
            # 匹配到行业后，收集该行业所有股票
            tickers = [t for t, v2 in sector_map.items()
                       if f'{v2.get("sector","")} / {v2.get("industry","")}' == sector]
            break

    # ── 手动加减标的 ──
    # 格式: "AAPL,-MSFT,GOOGL" → 添加 AAPL、GOOGL，剔除 MSFT
    if custom:
        for part in custom.replace("，", ",").split(","):  # 支持中英文逗号
            t = part.strip().upper()
            if t.startswith("-"):
                t = t[1:]  # 去掉 - 前缀
                if t in tickers:
                    tickers.remove(t)  # 从股票池中移除
            elif t:
                tickers.append(t)  # 手动添加

    tickers = sorted(set(tickers))[:15]  # 去重排序，最多 15 只
    if not tickers:
        return "<div class='text-secondary'>该行业无股票数据</div>"

    # ── 加载基本面数据 ──
    fundamentals = {}
    if _Path("data/fundamental_cache.json").exists():
        fundamentals = _json.loads(_Path("data/fundamental_cache.json").read_text(encoding="utf-8"))

    # ── 通过 westock-data 获取实时价格 ──
    import subprocess as _sp
    prices = {}
    westock_js = str(_Path.home() / ".workbuddy/plugins/marketplaces/cb_teams_marketplace/"
                     "plugins/finance-data/skills/westock-data/scripts/index.js")
    for t in tickers[:10]:  # 最多查 10 只
        try:
            # 调用 westock-data 的 quote 命令获取美股实时行情
            out = _sp.run(["node", westock_js, "quote", f"us{t}"],
                          capture_output=True, text=True, timeout=10,
                          cwd=_Path(westock_js).parent).stdout
            # 解析表格输出
            for line in out.split("\n"):
                line = line.strip()
                if not line.startswith("| us"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 15:
                    prices[t] = {"price": parts[6], "pe": parts[15], "chg": parts[9]}
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError, ValueError, IndexError):
            pass  # 单只股票查询失败不影响整体

    # ── 构建股票信息表 ──
    rows = ["| Ticker | PE | 价格 | 涨跌 |"]
    rows.append("|--------|-----|------|------|")
    for t in tickers[:12]:  # 最多展示 12 行
        f = fundamentals.get(t, {})
        p = prices.get(t, {})
        pe = f"{f.get('pe_ratio','?'):.0f}" if f.get('pe_ratio') else "?"  # 市盈率
        price = p.get("price", "?")    # 当前价格
        chg = p.get("chg", "?")        # 涨跌幅
        rows.append(f"| {t} | {pe} | {price} | {chg} |")

    # ── 构建 LLM Prompt ──
    prompt = f"""[Role] 你是 {analyst} 的投资决策模拟器。
[画像] {portrait}
[准确率] {acc_text}
[任务] 从 {sector} 行业选 3-5 只最符合其理念的标的。理由引用画像维度，仓位总和100%，入场区间+止损。
[股票池]\n{chr(10).join(rows)}
Output: 中文 Markdown。"""

    # ── 调用 LLM ──
    try:
        return chat(messages=[{"role": "user", "content": prompt}],
                    role="analyzer", max_tokens=4096, temperature=0.5)
    except Exception as e:
        return f"<div class='text-secondary'>LLM 调用失败: {e}</div>"


def _handle_portfolio_analysis(payload: dict) -> str:
    """处理持仓分析 LLM 调用。

    业务逻辑:
        1. 校验输入文本长度（至少 10 字符）
        2. 加载所有分析师的"全量"画像摘要（前 800 字符）
        3. 加载分析师 30 日胜率数据
        4. 构建分析 Prompt 调用 LLM
        5. 返回针对每只持仓的分析建议

    Args:
        payload: 前端传来的 JSON，包含:
            - text (str): 用户持仓描述文本

    Returns:
        LLM 生成的持仓分析 HTML/Markdown 内容
    """
    import json as _json
    from pathlib import Path as _Path
    from src.ai.llm_client import chat

    # ── 提取并校验输入 ──
    text = payload.get("text", "")
    if not text or len(text.strip()) < 10:
        return "<div class='text-secondary'>请输入至少 10 个字符的持仓描述</div>"

    # ── 加载所有分析师的"全量"画像摘要 ──
    # 全量画像 = 基于全部历史推文生成的完整投资画像
    portraits = []
    for fp in sorted(_Path("data/pipeline").glob("*全量*portrait.md")):
        username = fp.stem.replace("_全量_portrait", "")  # 提取用户名
        portraits.append(f"## {username}\n{fp.read_text(encoding='utf-8')[:800]}")

    # ── 加载准确率数据 ──
    acc_text = ""
    for fp in _Path("data/accuracy").glob("*_accuracy.json"):
        u = fp.stem.replace("_accuracy", "")
        d = _json.loads(fp.read_text(encoding="utf-8"))
        wr = d.get("returns_30d", {}).get("win_rate")
        if wr is not None:
            acc_text += f"- {u}: 30日胜率 {wr*100:.0f}%\n"

    # ── 构建分析 Prompt ──
    prompt = f"""你是投资顾问。基于分析师画像和准确率，分析我的持仓。
[分析师画像]\n{chr(10).join(portraits)}
[准确率]\n{acc_text}
[我的持仓]\n{text}
每只给出: 1)分析师视角看法(引用画像) 2)仓位/成本/止损建议 3)风险提示。中文Markdown。"""

    # ── 调用 LLM ──
    try:
        return chat(messages=[{"role": "user", "content": prompt}],
                    role="analyzer", max_tokens=4096, temperature=0.5)
    except Exception as e:
        return f"<div class='text-secondary'>LLM 调用失败: {e}</div>"
