"""
流水线任务执行器 —— 项目核心执行引擎
=======================================================

## 整体架构
本模块是整个项目的"CPU"，负责按顺序调度和执行各类数据处理任务。
采用 **单线程顺序执行** 模型，通过数据库（SQLite）在多进程间同步任务状态，
避免并发写入冲突。

## 流水线架构（Pipeline Architecture）
整个数据流水线由 6 种任务类型组成，按调用顺序排列：

    filter ──► analyze ──► portrait ──► clean
                   │
                   ├──► fetch_price（并行支线，拉取股票K线）
                   └──► fetch_crypto（并行支线，拉取加密货币行情）

任务执行链路说明：
1. **filter**   — LLM 过滤推文是否为投资相关
2. **analyze**  — LLM 深度分析单条投资推文（话题/立场/置信度/操作建议）
                 分析时自动注入 stock/price 上下文和媒体图片
3. **fetch_price**  — 通过 Polygon.io 拉取股票历史 K 线数据
4. **fetch_crypto** — 通过 Polygon.io 拉取加密货币历史行情（X: 前缀）
5. **portrait** — 汇总用户所有已分析推文，LLM 生成投资风格画像
6. **clean**    — 用 stock_alias.csv 清洗已分析数据中的股票别名

## 线程安全设计
- `_executor_lock`：全局互斥锁，确保同一时间只有一个后台线程在执行任务
- `_current_task_id`：记录当前正在执行的任务 ID，供 UI 轮询进度
- `_progress`：进度字典，供前端通过 get_progress() 获取实时状态

## 关键设计决策
- **单线程串行**而非多线程并行：因为 LLM API 有频率限制，串行调用更稳定
- **数据库驱动状态**：每个任务的 status 字段驱动状态机 pending→running→done/failed
- **重试机制**：analyze 任务单条重试 3 次，fetch_price 重试 2 次
- **模块级 CSV 缓存**：alias 映射表只加载一次，避免重复 IO
"""
from __future__ import annotations

import csv
import json
import re
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

from src.storage.database import db
from src.storage.models import PipelineTask


# ═══════════════════════════════════════════════════════════════════════
# 全局状态 —— 单线程执行器状态管理
# ═══════════════════════════════════════════════════════════════════════

# 单线程互斥锁：保证同一时间只有一个后台线程在执行任务
# 设计意图：LLM API 有频率限制，多线程并行会导致 429；同时避免多线程
# 同时写 SQLite 和 JSON 文件造成数据损坏
_executor_lock = threading.Lock()

# 当前正在执行的任务 ID，None 表示空闲
# 供 UI 层通过 is_running() 轮询判断执行器状态
_current_task_id: int | None = None

# 模块级 alias 缓存：stock_alias.csv 映射表只加载一次
# 避免每个 analyze 任务都重复打开/解析 CSV 文件
_alias_cache: dict[str, str] | None = None


def _load_alias() -> dict[str, str]:
    """加载股票别名映射表（模块级缓存）。
    
    从 data/stock_alias.csv 读取别名→标准名的映射关系。
    第一列是别名（如 "TSLA"），第二列是标准名（如 "TSLA" 或留空表示删除）。
    解析时跳过以 # 开头的注释行和空行。
    
    Returns:
        dict[str, str]: 别名 → 标准名 的映射字典
        
    缓存策略：
        首次调用时解析 CSV 并存入模块级 _alias_cache，
        后续调用直接返回缓存，避免重复 IO
    """
    global _alias_cache
    if _alias_cache is not None:  # 已缓存则直接返回
        return _alias_cache
    _alias_cache = {}
    alias_path = Path("data/stock_alias.csv")
    if alias_path.exists():
        with open(alias_path, encoding="utf-8") as f:
            for row in csv.reader(f):
                # 跳过注释行、空行和列数不足的行
                if row and not row[0].startswith("#") and len(row) >= 2 and row[0].strip() and row[1].strip():
                    _alias_cache[row[0].strip()] = row[1].strip()
    return _alias_cache


def _clean_analysis() -> dict:
    """数据清洗任务：用 stock_alias.csv 校准已分析推文中的股票别名。

    遍历 data/pipeline/ 下所有 *_analyzed.json 文件，
    将其中的 mentioned_stocks 列表中的别名统一替换为标准名称。
    这解决了同一只股票在不同推文中被引用为不同名称的问题。

    流程：
        1. 加载 alias 映射表
        2. 遍历所有 *_analyzed.json 文件
        3. 对每条推文的 mentioned_stocks 做别名→标准名映射
        4. 标记已修改的条目（_cleaned = True）
        5. 回写 JSON 文件

    Returns:
        dict: {"ok": True, "cleaned": 清洗的记录数}
    """
    alias = _load_alias()
    cleaned = 0
    # 按文件名排序，保证处理顺序可预测
    for fp in sorted(Path("data/pipeline").glob("*_analyzed.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        updated = False
        for item in data:
            stocks = item.get("mentioned_stocks", [])
            if stocks:
                # 核心清洗逻辑：每个股票名查 alias 表，找不到则保留原名
                mapped = [alias.get(s.strip(), s.strip()) for s in stocks]
                if mapped != stocks:  # 只有真正变化了才标记和更新
                    item["mentioned_stocks"] = mapped
                    item["_cleaned"] = True  # 标记该条目已被清洗
                    updated = True
                    cleaned += 1
        if updated:
            # 只有修改过的文件才回写，减少不必要的 IO
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return {"ok": True, "cleaned": cleaned}


# ═══════════════════════════════════════════════════════════════════════
# 进度与状态查询 —— 供 UI/API 层调用
# ═══════════════════════════════════════════════════════════════════════

# 全局进度状态，由 execute_tasks() 实时更新，get_progress() 读取
_progress: dict = {"total": 0, "done": 0, "msg": ""}


def get_progress() -> dict:
    """获取当前任务执行进度（返回拷贝，防止外部修改内部状态）。
    
    Returns:
        dict: {"total": 总任务数, "done": 已完成数, "msg": 状态消息}
    """
    return dict(_progress)


def is_running() -> bool:
    """检查执行器是否正在运行。
    
    Returns:
        bool: True 表示有任务正在执行
    """
    return _current_task_id is not None


# ═══════════════════════════════════════════════════════════════════════
# 任务调度入口
# ═══════════════════════════════════════════════════════════════════════

def execute_tasks(task_ids: list[int]) -> None:
    """后台线程入口：按指定 ID 列表顺序逐条执行流水线任务。
    
    这是整个流水线的主调度函数。通常在后台线程中调用。
    
    执行流程：
        1. 获取全局互斥锁（_executor_lock），如果已有任务在执行则直接返回
        2. 从数据库加载任务列表，过滤出 status=pending 的任务
        3. 按 ID 升序逐条执行：
           a. 将任务状态设为 running
           b. 根据 task_type 调用对应的执行函数
           c. 将执行结果写入 result 字段
           d. 根据结果更新状态为 done 或 failed
        4. 每条任务之间有 0.3 秒的 CPU 让出间隔

    任务 → 执行函数的映射关系：
        "filter"       → _filter_tweets()      推文过滤
        "fetch_price"  → _fetch_price()        股票行情拉取
        "fetch_crypto" → _fetch_crypto()       加密货币行情拉取
        "analyze"      → _analyze_tweet()      推文分析
        "portrait"     → _generate_portrait()  用户画像生成
        "clean"        → _clean_analysis()     数据清洗

    Args:
        task_ids: 待执行的任务 ID 列表
    """
    global _current_task_id

    # 尝试获取互斥锁，非阻塞模式
    # 如果已有任务在跑（锁被占用），直接返回，不排队
    if not _executor_lock.acquire(blocking=False):
        return  # 已有任务在执行

    try:
        # 从数据库加载所有指定 ID 的任务
        session = db.get_session()
        tasks = session.query(PipelineTask).filter(PipelineTask.id.in_(task_ids)).all()
        pending = [t for t in tasks if t.status == "pending"]  # 只取待执行的任务
        session.close()

        if not pending:
            return

        # 初始化进度计数器
        _progress["total"] = len(pending)
        _progress["done"] = 0
        _progress["msg"] = "准备执行..."

        # 逐条顺序执行
        for i, task in enumerate(pending):
            _current_task_id = task.id  # 标记当前任务 ID
            session = db.get_session()
            try:
                # 重新从数据库加载任务，确保拿到最新状态
                t = session.query(PipelineTask).get(task.id)
                t.status = "running"  # 状态机：pending → running
                session.commit()
                _progress["done"] = i
                _progress["msg"] = f"执行 {t.task_type} #{t.id}..."

                # JSON 反序列化任务参数
                payload = json.loads(t.payload)

                # ── 任务类型分发路由 ──
                if t.task_type == "filter":
                    result = _filter_tweets(payload)
                elif t.task_type == "fetch_price":
                    result = _fetch_price(payload["ticker"])
                elif t.task_type == "fetch_crypto":
                    result = _fetch_crypto(payload["ticker"])
                elif t.task_type == "analyze":
                    result = _analyze_tweet(payload)
                elif t.task_type == "portrait":
                    result = _generate_portrait(payload["username"])
                elif t.task_type == "clean":
                    result = _clean_analysis()
                elif t.task_type and t.task_type.startswith("governance_"):
                    result = _dispatch_governance_task(t.task_type, payload)
                else:
                    result = {"error": f"未知任务类型: {t.task_type}"}

                # 写入执行结果
                t.result = json.dumps(result, ensure_ascii=False)
                # 根据结果中是否有 "error" 键决定最终状态
                t.status = "done" if "error" not in result else "failed"
                t.error_msg = result.get("error")
                t.updated_at = None  # 让 ORM 自动更新为当前时间
                session.commit()
            except Exception as exc:
                # 捕获执行函数中未处理的异常
                t.status = "failed"
                t.error_msg = str(exc)[:500]  # 截断过长的错误信息
                session.commit()
            finally:
                session.close()
                time.sleep(0.3)  # 让出 CPU，避免持续占用

        # 所有任务执行完毕
        _progress["done"] = len(pending)
        _progress["msg"] = "全部完成"
        _current_task_id = None  # 清除任务 ID 标记
    finally:
        # 无论如何都要释放锁，避免死锁
        _executor_lock.release()


# ── 具体执行逻辑 ──

# ═══════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════

import yaml as _yaml
with open(Path(__file__).parent.parent.parent / "config" / "pipeline.yaml", encoding="utf-8") as _f:
    _PIPELINE_CFG = _yaml.safe_load(_f) or {}
POLYGON_KEY = _PIPELINE_CFG.get("api", {}).get("polygon_key", "")  # Polygon.io API 密钥
PRICES_PATH = Path("data/prices.json")  # 股票价格缓存文件
CRYPTO_PRICES_PATH = Path("data/crypto_prices.json")  # 加密货币价格缓存文件


# ═══════════════════════════════════════════════════════════════════════
# 行情拉取 —— Polygon.io API
# ═══════════════════════════════════════════════════════════════════════

def _fetch_price(ticker: str) -> dict:
    """拉取股票历史日K线数据（通过 Polygon.io）。
    
    调用 _fetch_polygon() 并将结果存入 data/prices.json。

    Args:
        ticker: 股票代码，如 "AAPL"

    Returns:
        dict: {"ok": True, "bars": K线条数} 或 {"error": "错误信息"}
    """
    return _fetch_polygon(ticker, PRICES_PATH)


def _fetch_crypto(ticker: str) -> dict:
    """拉取加密货币历史行情（通过 Polygon.io，X: 前缀）。
    
    Polygon.io 对加密货币使用 "X:符号USD" 格式的 ticker，
    例如 BTC → X:BTCUSD。

    Args:
        ticker: 加密货币符号，如 "BTC"

    Returns:
        dict: {"ok": True, "bars": K线条数} 或 {"error": "错误信息"}
    """
    return _fetch_polygon(f"X:{ticker}USD", CRYPTO_PRICES_PATH)


def _fetch_polygon(ticker: str, store_path: Path) -> dict:
    """通过 Polygon.io API 拉取日线聚合数据并缓存到本地 JSON 文件。
    
    拉取策略：
        - 请求范围：从配置的 polygon_from_date（默认 2015-01-01）到当日
        - 每次最多拉取 5000 条（limit=5000）
        - 支持 2 次重试，遇到 429 限流等待 15 秒后重试
        - 结果追加合并到本地 JSON 文件（不覆盖其他 ticker 的数据）

    Args:
        ticker:  完整 ticker 字符串（如 "AAPL" 或 "X:BTCUSD"）
        store_path: 本地缓存 JSON 文件路径

    Returns:
        dict: {"ok": True, "bars": K线条数} 或 {"error": "..."}
    """
    from datetime import date
    from_date = _PIPELINE_CFG.get("api", {}).get("polygon_from_date", "2015-01-01")
    to_date = date.today().strftime("%Y-%m-%d")  # 动态 end date，拉到今天
    
    # 构造 Polygon.io 聚合数据 API URL
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
           f"{from_date}/{to_date}?apiKey={POLYGON_KEY}&limit=5000")
    
    for attempt in range(2):  # 最多重试 2 次
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            
            if resp.get("resultsCount", 0) > 0:  # 有数据才处理
                prices = {}
                if store_path.exists():
                    # 读取已有缓存，追加而非覆盖
                    prices = json.loads(store_path.read_text(encoding="utf-8"))
                prices[ticker] = resp  # 以 ticker 为 key 存储完整响应
                store_path.write_text(json.dumps(prices, ensure_ascii=False), encoding="utf-8")
                return {"ok": True, "bars": resp["resultsCount"]}
            
            return {"error": "无数据"}
        except urllib.error.HTTPError as e:
            if e.code == 429:  # 限流：等待 15 秒后重试
                time.sleep(15)
                continue
            return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": str(e)}
    
    return {"error": "重试失败"}


# ═══════════════════════════════════════════════════════════════════════
# 价格上下文注入 —— 为分析结果附加 K 线摘要和基本面数据
# ═══════════════════════════════════════════════════════════════════════

def _enrich_price_context(stocks: list[str], created_at: str) -> list[dict]:
    """为推文分析结果注入 K 线摘要 + 基本面数据，标记是否可回测。
    
    这是连接"分析"和"数据"的关键函数。在 analyze 任务完成后，
    自动为推文中提到的每只股票附加以下上下文：

    1. 推文发布当日的收盘价
    2. 推文前 30 天的涨跌幅百分比
    3. 最新收盘价
    4. 基本面数据（PE、ROE、营收增长率、行业）
    5. backward_available 标志：推文之后是否有 K 线数据（用于后续回测判断）

    backward_available 的含义：
        True  = 推文发布后有 K 线数据 → 可进行回测验证
        False = 只有推文前的数据 → 无法判断预测是否正确

    Args:
        stocks: 股票代码列表（最多处理前 10 只）
        created_at: 推文发布时间字符串

    Returns:
        list[dict]: 每只股票的上下文信息列表
    """
    if not stocks:
        return []
    result = []
    prices_db = {}
    fundamentals = {}
    
    # 加载价格缓存
    if PRICES_PATH.exists():
        prices_db = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
    
    # 加载基本面数据缓存
    f_fp = Path("data/fundamental_cache.json")
    if f_fp.exists():
        fundamentals = json.loads(f_fp.read_text(encoding="utf-8"))

    # 将推文发布时间转为 Unix 时间戳（秒）
    tweet_ts = 0
    if created_at:
        try:
            from datetime import datetime
            tweet_ts = int(datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S").timestamp())
        except Exception:
            pass

    for ticker in stocks[:10]:  # 最多处理 10 只股票，防止上下文过长
        ctx = {
            "ticker": ticker,
            "backward_available": False,  # 默认不可回测
            "price_summary": None,
            "fundamentals": None
        }
        price_data = prices_db.get(ticker, {})
        
        if price_data and price_data.get("results"):
            bars = price_data["results"]  # Polygon 返回的 K 线数组
            
            if tweet_ts and bars:
                # ── 按推文时间切片 K 线数据 ──
                # before: 推文发布之前（含当日）的 K 线
                before = [b for b in bars if b.get("t", 0) / 1000 <= tweet_ts]
                # after:  推文发布之后的 K 线
                after = [b for b in bars if b.get("t", 0) / 1000 > tweet_ts]
                
                if before:
                    last_close = before[-1].get("c", 0)  # 推文当日收盘价
                    # 计算推文前 30 天涨跌幅
                    pct_30d = round(
                        (last_close - before[0].get("c", last_close)) / before[0].get("c", 1) * 100,
                        1
                    ) if len(before) > 1 else 0
                    ctx["price_summary"] = {
                        "close_at_tweet": last_close,
                        "pct_30d_before": pct_30d,
                        "recent_close": bars[-1].get("c", last_close)
                    }
                
                # 如果推文后有 K 线，标记可回测
                if after:
                    ctx["backward_available"] = True
            else:
                # 无推文时间或时间解析失败时，仅提供最新收盘价
                if bars:
                    ctx["price_summary"] = {"recent_close": bars[-1].get("c", 0)}
        
        # ── 注入基本面数据 ──
        f = fundamentals.get(ticker, {})
        if f:
            ctx["fundamentals"] = {
                "pe": f.get("pe_ratio"),           # 市盈率
                "roe": f.get("roe"),               # 净资产收益率
                "revenue_growth": f.get("revenue_growth"),  # 营收增长率
                "sector": f.get("sector", "")      # 所属行业
            }
        result.append(ctx)
    
    return result


# ═══════════════════════════════════════════════════════════════════════
# 推文分析 —— LLM 深度分析
# ═══════════════════════════════════════════════════════════════════════

def _analyze_tweet(payload: dict) -> dict:
    """调用 LLM 对单条推文进行结构化投资分析。
    
    LLM 输出的 JSON 包含以下字段：
        - topic: 话题分类（个股分析/行业研判/宏观分析/加密货币/操作记录...）
        - mentioned_stocks: 提及的股票代码列表
        - mentioned_crypto: 提及的加密货币列表
        - mentioned_sectors: 涉及的行业/板块
        - stance: 态度倾向（看多/看空/中性/观望/无明确方向）
        - confidence: 置信度（high/medium/low）
        - reasoning_chain: 推理链（一段连贯的分析文本）
        - action_hint: 操作暗示（买入/卖出/持有/加仓/减仓/观望/无）
        - key_quote: 关键引用（推文中最能代表观点的句子）
        - image_analysis: 配图分析（如果有图片的话）

    处理流程：
        1. 从数据库加载该推文关联的本地图片路径
        2. 构造分析 prompt（含推文文本、上下文标记、时间）
        3. 调用 chat_vision 多模态 LLM（最多传递 3 张图片）
        4. 解析/清洗 LLM 输出的 JSON
        5. 用 alias 表规范化股票代码
        6. 注入 K 线 + 基本面价格上下文
        7. 保存到 *_analyzed.json 文件

    重试策略：单条推文最多重试 3 次，每次失败间隔 5 秒

    Args:
        payload: 任务参数，含 tweet_id, username, text, created_at 等

    Returns:
        dict: {"ok": True} 或 {"error": "错误详情"}
    """
    import re

    from src.ai.llm_client import chat_vision
    from src.storage.models import Media

    # ── 加载该推文关联的图片 ──
    session = db.get_session()
    img_paths = []
    try:
        for m in session.query(Media).filter(
            Media.tweet_id == payload.get("tweet_id"), Media.downloaded == True
        ).all():
            if m.local_path:
                img_paths.append(m.local_path)
    finally:
        session.close()

    alias = _load_alias()

    # ── 构造分析 Prompt ──
    PROMPT = (
        '分析推文,仅输出JSON: {"topic":"个股分析|行业研判|宏观分析|加密货币|操作记录|投资策略|信息分享|招聘/人脉|其他",'
        '"mentioned_stocks":[],"mentioned_crypto":[],"mentioned_sectors":[],'
        '"stance":"看多|看空|中性|观望|无明确方向","confidence":"high|medium|low",'
        '"reasoning_chain":"","action_hint":"买入|卖出|持有|加仓|减仓|观望|无",'
        '"key_quote":"","image_analysis":null}\n\n'
    )
    # 构造上下文（推文文本 + 元信息）
    ctx = [payload.get("text", "")]
    if payload.get("is_reply"):
        ctx.append(f"回复 @{payload.get('replied_to_user', '?')}")
    if payload.get("is_quote"):
        ctx.append(f"引用 @{payload.get('quoted_user', '?')}")
    ctx.append(f"时间: {payload.get('created_at', '?')}")
    prompt = PROMPT + "\n".join(ctx)

    # ── LLM 调用 + JSON 解析（最多重试 3 次） ──
    for retry in range(3):
        try:
            # 多模态调用：同时传入文本和图片
            resp = chat_vision(text_prompt=prompt, image_paths=img_paths[:3], role="analyzer")
            # 清理 LLM 输出中可能包裹的 markdown 代码块标记
            clean = resp.strip().lstrip("```json").rstrip("```").strip()
            result = json.loads(clean)
            
            # ── 规范化股票代码 ──
            stocks = result.get("mentioned_stocks", [])
            norm = []
            for s in stocks:
                s = str(s).strip().lstrip("$")  # 去掉 $ 前缀
                if s in alias:
                    if alias[s]:  # alias 表中有映射
                        norm.append(alias[s])
                    # alias[s] 为空表示该别名被配置为应删除，跳过
                elif re.match(r"^[A-Za-z0-9.]+$", s):
                    norm.append(s.upper())  # 纯字母数字 → 大写
                else:
                    norm.append(s)  # 中文股票名等，保留原样
            result["mentioned_stocks"] = list(dict.fromkeys(norm))  # 去重保序
            
            # ── 附加原始推文元信息 ──
            result["tweet_id"] = payload.get("tweet_id")
            result["twitter_id"] = payload.get("tweet_id_str", "")
            result["text"] = payload.get("text", "")
            result["created_at"] = payload.get("created_at", "")
            
            # ── 注入 K 线 + 基本面上下文（核心增值功能） ──
            result["price_context"] = _enrich_price_context(
                result["mentioned_stocks"], payload.get("created_at", "")
            )
            
            _save_analyzed(payload.get("username", ""), result)
            time.sleep(20)  # LLM API 冷却间隔
            return {"ok": True}
            
        except (json.JSONDecodeError, ConnectionError, OSError) as exc:
            if retry < 2:  # 还有重试机会
                time.sleep(5)
                continue
            return {"error": f"API 失败: {exc}"}
    
    return {"error": "重试失败"}


def _save_analyzed(username: str, result: dict) -> None:
    """将分析结果追加保存到按用户+月份分组的 JSON 文件。
    
    文件命名规则：data/pipeline/{username}_{YYYY-MM}_analyzed.json
    这样设计是为了：
        1. 避免单个文件过大（按月分片）
        2. 方便按时间窗口查询（portrait 生成时需要）
        3. 减少写入时的锁竞争（不同月份写入不同文件）

    Args:
        username: 推特用户名
        result: 分析结果字典（必须含 tweet_id 和 created_at）
    """
    # 根据推文日期提取月份标签（如 "2024-01"）
    created = result.get("created_at", "")
    month = created[:7] if created else "unknown"
    fp = Path(f"data/pipeline/{username}_{month}_analyzed.json")
    
    # 加载已有数据
    existing = []
    if fp.exists():
        existing = json.loads(fp.read_text(encoding="utf-8"))
    
    # 去重：以 tweet_id 为 key 防止重复写入
    ids = {r["tweet_id"] for r in existing if "tweet_id" in r}
    if result.get("tweet_id") not in ids:
        existing.append(result)
        fp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# 用户画像生成 —— LLM 汇总分析
# ═══════════════════════════════════════════════════════════════════════

def _generate_portrait(username: str) -> dict:
    """汇总用户所有已分析推文，调用 LLM 生成投资风格画像。
    
    username 参数支持两种格式：
    
    格式 A（时间窗口）：TJ_Research_1个月
        → user=TJ_Research, window=30 天
        支持窗口：1个月/3个月/6个月/1年/全量
    
    格式 B（日期范围）：TJ_Research_2024-01-01_2024-06-30
        → user=TJ_Research, 精确日期范围过滤

    画像包含 12 个维度（v2 升级版，注入"女娲"思维提炼方法论）：
        1. 投资哲学      2. 心智模型（三重验证）       3. 核心板块
        4. 操作风格      5. 决策启发式（if-then规则）  6. 仓位管理与Beta调节
        7. 风险偏好      8. 反模式（绝不做什么）       9. 情绪与表达DNA
        10. 预测准确率   11. 进化轨迹                  12. 诚实边界
        13. 智识谱系 + 一句话总结

    Args:
        username: "用户名_窗口" 或 "用户名_开始日期_结束日期" 格式

    Returns:
        dict: {"ok": True, "path": 输出文件路径, "window": 窗口标签, "tweets": 推文数}
              或 {"error": "错误信息"}
    """
    from src.ai.llm_client import chat
    from datetime import datetime, timedelta

    # ── 解析用户名 + 时间窗口 ──
    m = re.match(r"(.+)_(1个月|3个月|6个月|1年|全量)$", username)
    use_date_range = False
    date_from = date_to = ""
    if m:
        user = m.group(1)
        window_label = m.group(2)
        window_map = {"1个月": 30, "3个月": 90, "6个月": 180, "1年": 365, "全量": 9999}
        window_days = window_map.get(window_label, 9999)
    else:
        m2 = re.match(r"(.+?)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", username)
        if m2:
            user = m2.group(1)
            date_from = m2.group(2)
            date_to = m2.group(3)
            window_label = f"{date_from} ~ {date_to}"
            window_days = 9999
            use_date_range = True
        else:
            return {"error": f"无法解析用户名+窗口: {username}"}

    # ── 加载该用户所有已清洗的分析数据 ──
    data = []
    for fp in Path("data/pipeline").glob(f"{user}_*_analyzed_cleaned.json"):
        data.extend(json.loads(fp.read_text(encoding="utf-8")))
    if not data:
        return {"error": "无分析数据"}

    # ── 时间窗口过滤 ──
    if use_date_range:
        windowed = [r for r in data if r.get("created_at", "") and date_from <= r["created_at"][:10] <= date_to]
    else:
        now = datetime.utcnow()
        cutoff = now - timedelta(days=window_days) if window_days < 9999 else datetime(2000, 1, 1)
        windowed = [r for r in data if r.get("created_at", "") and r["created_at"][:10] >= cutoff.strftime("%Y-%m-%d")]
    
    if not windowed:
        return {"error": f"时间窗口 {window_label} 内无推文" if not use_date_range else f"日期范围 {date_from}~{date_to} 内无推文"}
    data = windowed

    # ── 丰富统计摘要（为 LLM 提炼心智模型提供更多维度）──
    from collections import Counter
    topics = Counter(r.get("topic", "?") for r in data)
    stances = Counter(r.get("stance", "?") for r in data)
    confidences = Counter(r.get("confidence", "?") for r in data)
    action_hints = Counter(r.get("action_hint", "?") for r in data)
    stocks = Counter()
    sectors = Counter()
    for r in data:
        for sd in r.get("stock_details", []):
            stocks[sd.get("ticker", "?")] += 1
            if sd.get("sector"):
                sectors[sd["sector"]] += 1
    times = sorted(r["created_at"][:10] for r in data if r.get("created_at"))

    # 抽取典型推文样本（供 LLM 分析表达风格：确定性措辞、类比使用、引用习惯等）
    sample_texts = []
    for r in data[-30:]:  # 最近 30 条
        txt = r.get("text", "") or r.get("key_quote", "")
        if txt and len(txt) > 20:
            sample_texts.append(txt[:200])

    # ── 构造画像生成 Prompt（v2 升级版，注入思维提炼方法论）──
    prompt = f"""你是投资分析 + 认知心理学交叉领域的专家。基于 {len(data)} 条 {user} 的推文分析结果和原始推文样本，生成一份"可操作的认知画像"——不只是描述他做了什么，更要揭示他**如何思考**。

## 基础数据
- 时间窗口: {window_label} ({times[0]} ~ {times[-1]})
- 话题分布: {dict(topics.most_common())}
- 态度分布: 看多{stances.get('看多',0)} 看空{stances.get('看空',0)} 观望{stances.get('观望',0)}
- 置信度分布: {dict(confidences)}
- 操作倾向: {dict(action_hints.most_common())}
- 重仓股: {dict(stocks.most_common(15))}
- 关注板块: {dict(sectors.most_common(10))}
- 最近推文样本（用于表达风格分析）:
{chr(10).join(f"  [{i+1}] {t}" for i,t in enumerate(sample_texts[:20]))}

## 输出要求（严格按以下结构）

### 1. 投资哲学（200字）
他如何看待市场？核心理念是什么？（价值/成长/动量/宏观？混合型就说明混合比例）

### 2. 心智模型（3-5个，每个需附证据）【核心升级维度】
提炼该投资者反复使用的**判断框架**——不是观点，而是他看问题的"镜片"。
每个心智模型必须满足以下格式：
```
**模型名**：一句话描述
- 证据A：[推文日期] "推文原文关键句..." → 对应场景
- 证据B：[推文日期] "推文原文关键句..." → 对应场景
- 应用方式：当遇到X类情况时，他会用这个模型如何判断
- 失效条件：这个模型在什么情况下会失灵
```
**筛选标准（三重验证）**：
- 跨域复现：在≥2 只不同股票/行业中用过这个框架？
- 生成力：能推断他对新问题的立场？（不只是复述他说过的话）
- 排他性：这个框架不是所有投资者通用的？（"买低卖高"不算）
只输出通过至少两重验证的模型。

### 3. 核心板块
板块偏好及权重，说明他对各板块的理解深度差异。

### 4. 操作风格
买入/卖出的节奏、持仓周期、是否做波段、对消息面的反应模式。

### 5. 决策启发式（5-10条 if-then 规则）【核心升级维度】
提炼他的**快速判断规则**——可表述为"如果 X，则 Y"的简洁行动指令。
每条格式：`如果 [触发条件]，则 [行动]` + 证据（推文日期 + 关键词）
优选级排序：最独特、最反直觉的规则排前面。
示例：
- 如果 纳指PE超过30x 且 持仓已有浮盈>20%，则 每涨2%减1/4仓位
- 如果 财报超预期 但 股价不涨反跌，则 警惕"利好出尽"

### 6. 仓位管理与 Beta 调节
重点分析：净仓位暴露范围、现金比例、降beta的触发条件、防御板块切换节奏、加仓/减仓的信号。

### 7. 风险偏好
对最大回撤的容忍度、是否使用杠杆/期权、对黑天鹅的态度。

### 8. 反模式（他绝对不会做什么，≥3条）【核心升级维度】
定义一个人的边界往往比定义他的能力圈更有信息量。
- 明确回避的操作："从不____"、"绝不____"
- 明确回避的标的类型
- 明确回避的市场行为
每条例证（如果推文中明确表达了，引用原话；如果是从行为推断的，标注为"推断"）

### 9. 情绪与表达 DNA【核心升级维度】
从推文样本中分析他的表达特征：
- 句式偏好：短句/长句？陈述/反问？类比密度高吗？
- 确定性表达：常用"大概率/可能"还是"一定/必然"？
- 幽默方式：讽刺/自嘲/荒诞/不幽默？
- 引用习惯：爱引用谁？引用什么类型的内容？
- 在极端行情下的情绪波动特征

### 10. 预测准确率（对照股价）
基于 accuracy/ 目录的回测数据，注明准确率来源（回测结果/自我评价/推断）。

### 11. 进化轨迹
思想是否在变化？标注具体的观点转变（从A→B，时间点+证据）。

### 12. 诚实边界（≥3 条具体局限）【核心升级维度】
**必须明确指出本画像的局限性**——这比画像本身更能帮助使用者避免误用。
- 信息来源局限（仅推文，无私下持仓信息）
- 某类场景缺失（如从未讨论过期权/加密货币/债市）
- 画像时间窗口局限（历史不代表未来）
- 自述偏差（公开表达≠真实操作）
- 任何感到不确定的地方请注明"不确定"

### 13. 智识谱系 + 一句话总结
- 他受谁影响？（从引用/推崇中推断）
- 他的独特之处是什么？
- 一句话总结（不超过 30 字）

---
输出规则：
- 只输出研究成果，不编造证据
- 如果某维度信息不足，写"信息不足"并说明缺什么，不要硬凑
- 引用推文原话时标注日期
- 推断 vs 确信要明确区分
- 诚实边界至少写 3 条具体局限"""

    # 调用 LLM 生成画像（v2 升级版需要更多输出 token）
    report = chat(messages=[{"role": "user", "content": prompt}], role="analyzer", max_tokens=16384, temperature=0.5)
    
    # ── 在输出文件头部写入元数据（v2 升级版）──
    meta = f"""---
user: {user}
window: {window_label}
tweets: {len(data)}
date_range: {times[0]} ~ {times[-1]}
generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
version: v2 (nuwa-enhanced — 心智模型/决策启发式/反模式/表达DNA/诚实边界)
---
"""
    out = Path(f"data/pipeline/{username}_portrait.md")
    out.write_text(meta + report, encoding="utf-8")
    return {"ok": True, "path": str(out), "window": window_label, "tweets": len(data)}


# ═══════════════════════════════════════════════════════════════════════
# 推文过滤 —— LLM 二分类（投资相关 / 非相关）
# ═══════════════════════════════════════════════════════════════════════

def _filter_tweets(payload: dict) -> dict:
    """过滤推文：判断每条推文是否与投资/金融/市场相关。

    支持两种模式：
    
    1. **filter_new（全量扫描模式）**：
       - 遍历所有用户的所有推文
       - 跳过已过滤的（通过已存在的 *_filtered.json 判断）
       - 批量调用 LLM 判断投资相关性
       - 按用户+月份分组写入 *_filtered.json
       - 适用场景：初始运行或定期全量更新
    
    2. **filter_single（单条模式）**：
       - 在 filter_new 基础上通过 tweet_id 筛选
       - 只处理指定的一条推文
       - 适用场景：UI 手动触发单条推文重分析

    过滤流程：
        1. 收集所有已过滤的 tweet ID（去重集合）
        2. 遍历每个用户：收集未过滤的推文
        3. 按 BATCH=20 条一批调用 LLM 进行批量判断
        4. 将结果按月份分组写入 JSON 文件

    判定标准：
        相关 → 股票、加密货币、期权、期货、宏观、行业、策略、仓位、
               基本面、财报、估值、技术分析、交易心理、市场情绪
        无关 → 日常生活、闲聊、娱乐、纯政治、纯表情、纯转发

    Args:
        payload: {"action": "filter_new"|"filter_single", "tweet_id": int (可选)}

    Returns:
        dict: {"ok": True, "new_filtered": 新增过滤数, "message": "..."}
    """
    from src.storage.database import db
    from src.storage.models import Tweet, User
    from src.ai.llm_client import chat

    # ── 过滤 Prompt：定义投资相关 vs 无关的标准 ──
    FILTER_PROMPT = """你是一个推文过滤器。判断每条推文是否与投资/金融/市场相关。
相关话题：股票、加密货币、期权、期货、宏观分析、行业分析、投资策略、仓位管理、公司基本面、财报、估值、技术分析、交易心理、市场情绪。
无关话题：日常生活、闲聊、娱乐、纯政治、纯表情、纯转发无评论。
输入是一批推文（JSON 数组），每条有 id 和 text。
输出严格 JSON 数组，每项格式：{"id": <tweet_id>, "is_investment_related": true/false}
只输出 JSON，不要解释。"""

    action = payload.get("action", "")
    single_tweet_id = payload.get("tweet_id")  # filter_single 模式下的目标推文 ID

    session = db.get_session()
    try:
        # ── 收集已过滤的 tweet ID（跨所有用户） ──
        done_ids = set()
        for fp in Path("data/pipeline").glob("*_filtered.json"):
            for t in json.loads(fp.read_text(encoding="utf-8")):
                done_ids.add(t.get("tweet_id"))  # 支持旧字段名
                done_ids.add(t.get("id"))        # 支持新字段名

        users = session.query(User).all()
        total_new = 0
        BATCH = 20  # 每批 20 条推文送 LLM 判断

        for u in users:
            # 获取该用户所有推文（按 ID 排序，保证可重复性）
            tweets = session.query(Tweet).filter(Tweet.user_id == u.id).order_by(Tweet.id).all()
            new = []
            
            # ── 收集待过滤推文 ──
            for t in tweets:
                # 跳过已过滤的推文
                if t.id not in done_ids and t.tweet_id not in done_ids and t.text:
                    # ★ filter_single vs filter_new 的核心区别：
                    # filter_single: 只处理指定的那一条推文，其余跳过
                    # filter_new: 处理所有未过滤的推文
                    if action == "filter_single" and single_tweet_id and t.id != single_tweet_id:
                        continue
                    new.append({
                        "id": t.id,
                        "tweet_id": t.tweet_id,
                        "text": t.text or "",
                        "created_at": t.created_at_twitter.isoformat(),
                        "is_reply": t.is_reply or False,
                        "is_quote": t.is_quote or False,
                        "replied_to_user": t.replied_to_user,
                        "quoted_user": t.quoted_user,
                        "quoted_text": t.quoted_text,
                        "has_media": t.has_media or False,
                    })

            if not new:
                continue  # 该用户没有新推文需要过滤

            # ── 分批调用 LLM 过滤 ──
            results = []
            for i in range(0, len(new), BATCH):
                batch = new[i:i + BATCH]  # 每次取 BATCH 条
                resp = chat(messages=[
                    {"role": "system", "content": FILTER_PROMPT},
                    {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
                ], role="filter", max_tokens=2048)
                # 清理 LLM 输出中的 markdown 代码块
                resp = resp.strip().lstrip("```json").rstrip("```").strip()
                try:
                    results.extend(json.loads(resp))
                except json.JSONDecodeError:
                    continue  # JSON 解析失败则跳过这批

            # 构建 id → is_investment_related 的快速查表
            filter_map = {r["id"]: r["is_investment_related"] for r in results}
            for t in new:
                t["is_investment_related"] = filter_map.get(t["id"], False)

            # ── 按月份分组写入（避免单文件过大） ──
            from collections import defaultdict
            monthly: dict[str, list[dict]] = defaultdict(list)
            for t in new:
                month_tag = t["created_at"][:7] if t.get("created_at") else "unknown"
                monthly[month_tag].append(t)

            for month_tag, month_tweets in monthly.items():
                tag = f"{u.username}_{month_tag}"
                out_path = Path(f"data/pipeline/{tag}_filtered.json")
                existing = []
                if out_path.exists():
                    existing = json.loads(out_path.read_text(encoding="utf-8"))
                # 去重：先收集已有 ID，再追加新数据
                existing_ids = {t["id"] for t in existing}
                for t in month_tweets:
                    if t["id"] not in existing_ids:
                        existing.append(t)
                out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
                total_new += len(month_tweets)

        session.close()
        return {"ok": True, "new_filtered": total_new, "message": f"已过滤 {total_new} 条新推文"}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# 信号治理任务桩
# ═══════════════════════════════════════════════════════════════════════

_GOVERNANCE_TASKS = {
    "governance_run",
    "governance_candidate",
    "governance_quality",
    "governance_risk",
    "governance_panel",
    "governance_debate",
    "governance_publish",
    "governance_report",
}


def _dispatch_governance_task(task_type: str, payload: dict) -> dict:
    """Dispatch governance task types to the real governance runner."""
    if task_type not in _GOVERNANCE_TASKS:
        return {"error": f"未知治理任务类型: {task_type}"}

    try:
        from src.governance.adapters import candidate_from_payload
        from src.governance.repository import GovernanceRepository
        from src.governance.runner import run_governance_for_candidate

        repo = GovernanceRepository(base_dir=payload.get("repo_base_dir", "data/governance"))
        candidate = candidate_from_payload(payload, repo=repo)
        result = run_governance_for_candidate(
            candidate,
            repo=repo,
            push_intent=payload.get("push_intent", "dashboard"),
            acknowledged_gaps=payload.get("acknowledged_gaps") or [],
            generate_report=bool(payload.get("generate_report", task_type == "governance_report")),
        )
        if result.error:
            return {"error": result.error, "signal_id": result.signal_id, "publish_status": result.publish_status}
        return {
            "ok": True,
            "signal_id": result.signal_id,
            "status": result.status,
            "publish_status": result.publish_status,
            "package_path": result.package_path,
            "report_path": result.report_path,
            "message": f"治理任务 {task_type} 已完成",
        }
    except Exception as exc:
        return {"error": str(exc), "signal_id": payload.get("signal_id", "")}
