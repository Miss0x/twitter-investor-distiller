"""Daemon 守护进程 — 轮转拉取推文 + 自动触发 filter → analyze 流水线。

本脚本为独立进程，由 web_api.py 通过 subprocess 启动，负责：
1. 轮转拉取监控用户的推文（从 users.json 读取监控列表）
2. 检测新推文后自动创建 PipelineTask（filter 类型）入队
3. 内置指数退避（exponential backoff）应对 Twitter API 限流

设计要点：
- 轮转调度：逐个用户轮流拉取（而非同时），降低限流风险
- 状态持久化：拉取进度、限流状态写入 data/auto_scheduler_state.json
- 容错恢复：遇到异常等待更长间隔后重试

运行方式：
    python scripts/daemon_worker.py
    # 通常由 web_api.py 的子进程管理器启动
"""
import json
import sys
import time
from pathlib import Path

# 将项目根目录加入 Python 搜索路径，确保 src 模块可导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.crawler.twitterapi_fetcher import TwitterAPIFetcher
from src.storage.database import db
from src.storage.models import PipelineTask


def run():
    """守护进程主循环。

    循环逻辑（无限轮询）：
    1. 加载监控用户列表（支持运行时热更新 users.json）
    2. 按轮转索引选择当前用户
    3. 拉取该用户最新推文（最多 1 页）
    4. 如果有新推文 → 为每条创建 filter PipelineTask 入队 + 记录统计
    5. 如果无限流 → 正常间隔 300 秒
    6. 如果遇到限流 → 指数退避，最多 8 倍间隔
    7. 如果拉取失败 → 长间隔重试
    8. 保存状态到 JSON，索引 +1 进入下一轮

    状态文件 data/auto_scheduler_state.json 内容：
    - user_idx: 当前轮转索引
    - total_fetched: 累计拉取推文数
    - db_count_{username}: 各用户数据库中已有推文数
    - rate_limited: 限流提示信息
    - updated: 最近更新时间
    """
    db.init_db()

    # 加载监控用户列表
    USERS = _load_users()
    INTERVAL = 300  # 基础拉取间隔：300秒 = 5分钟，避免频繁触发 Twitter 限流
    fetcher = TwitterAPIFetcher()

    # 状态文件：记录轮转进度和限流信息
    state = Path("data/auto_scheduler_state.json")
    st = json.loads(state.read_text()) if state.exists() else {}

    # 从状态文件恢复上次的轮转索引（支持中断后继续）
    idx = st.get("user_idx", 0)
    backoff = 1  # 指数退避倍数，初始为 1x

    while True:
        try:
            # 热更新：每次循环重新读取用户列表（支持运行时增删用户）
            USERS = _load_users() or USERS

            # 轮转选择当前用户
            username = USERS[idx % len(USERS)]
            st["user_idx"] = (idx + 1) % len(USERS)
            st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # 查询数据库中该用户已有推文数（用于状态展示）
            last_ts = fetcher.get_last_tweet_ts(username)
            db_cnt = fetcher.get_user_tweet_count(username)
            st[f"db_count_{username}"] = db_cnt

            # 拉取推文：最多 1 页，避免单次耗时过长
            res = fetcher.fetch_tweets(username, max_pages=1, since_ts=last_ts)
            new_cnt = res.get("total_new", 0)

            if res.get("ok") and new_cnt > 0:
                # --- 成功拉取到新推文 ---
                st["total_fetched"] = st.get("total_fetched", 0) + new_cnt

                # 为每条新推文创建 filter 类型的 PipelineTask
                session = db.get_session()
                for _ in range(new_cnt):
                    t = PipelineTask(
                        task_type="filter",           # 标记为过滤任务
                        status="pending",              # 初始状态：等待处理
                        payload=json.dumps({
                            "action": "filter_latest",
                            "user": username,
                        }),
                    )
                    session.add(t)
                session.commit()
                session.close()

                # 成功拉取：清除限流标记，恢复退避
                st.pop("rate_limited", None)
                backoff = max(1, backoff // 2)
                print(f"[DAEMON] {username}: +{new_cnt} tweets, pipeline triggered")

            elif new_cnt == 0 and res.get("ok"):
                # --- 正常但无新推文 ---
                st.pop("rate_limited", None)
                print(f"[DAEMON] {username}: 无新推文")

            elif "rate limit" in str(res.get("error", "")).lower():
                # --- 触发 Twitter API 限流 ---
                # 指数退避：backoff 翻倍，最多 8 倍（即最长 2400 秒 = 40 分钟间隔）
                backoff = min(backoff * 2, 8)
                st["rate_limited"] = f"限流, {INTERVAL * backoff}s 后重试"
                print(f"[DAEMON] {username}: rate limited, backoff x{backoff}")

            else:
                # --- 其他错误 ---
                print(f"[DAEMON] {username}: {res.get('error', '')}")

            # 每次循环结束时保存状态
            state.write_text(json.dumps(st, ensure_ascii=False))
            idx += 1

            # 等待下次拉取：基础间隔 × 退避倍数
            time.sleep(INTERVAL * backoff)

        except Exception as exc:
            # 未预期的异常：等待 2 倍基础间隔后重试
            print(f"[DAEMON] error: {exc}")
            time.sleep(INTERVAL * 2)


def _load_users():
    """加载监控用户列表。

    优先从 data/users.json 读取，若文件不存在则使用默认列表。

    Returns:
        list[str]: Twitter 用户名列表（不含 @ 前缀）

    默认监控用户：
    - TJ_Research: 科技股研究分析师
    - dearbaibabybus: 宏观分析博主
    """
    fp = Path("data/users.json")
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    # 默认监控列表（硬编码后备）
    return ["TJ_Research", "dearbaibabybus"]


if __name__ == "__main__":
    run()
