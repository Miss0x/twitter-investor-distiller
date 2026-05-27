"""#3 实时触发 — Phase 4

轮询数据库中新入库的推文，自动创建 filter 类型的 PipelineTask 入队，
由流水线处理器消费执行 filter → analyze 流程。

核心特性：
- DB 轮询：监控 Tweet 表的主键 ID 增长，检测新增推文
- 日预算控制：每天最多创建 DAILY_BUDGET 个 analyze 任务，防止 API 费用失控
- 去重保护：检查是否已存在对应的 filter 任务，避免重复创建
- 状态持久化：记录上次检查到的最大 tweet_id，支持中断续跑

用法：
    python scripts/auto_scheduler.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from src.storage.database import db
from src.storage.models import Tweet, PipelineTask

DAILY_BUDGET = 20      # 每天最多自动创建的 analyze 任务数（控制 OpenAI API 消耗）
POLL_INTERVAL = 60     # 数据库轮询间隔（秒）


def get_last_checked_id() -> int:
    """从状态文件读取上次处理到的最大 tweet ID。

    该 ID 用于增量检测新推文——只查询 id > last_id 的记录，
    避免每次轮询都扫描全表。

    Returns:
        int: 上次检查到的 tweet 自增 ID，首次运行返回 0
    """
    state = Path("data/auto_scheduler_state.json")
    if state.exists():
        return json.loads(state.read_text()).get("last_id", 0)
    return 0


def save_last_checked_id(tweet_id: int) -> None:
    """保存最新处理到的 tweet ID 到状态文件。

    状态文件同时记录更新时间，便于排查调度器是否正常运行。

    Args:
        tweet_id: 本次处理的最新 tweet 自增 ID
    """
    Path("data/auto_scheduler_state.json").write_text(
        json.dumps({
            "last_id": tweet_id,
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
    )


def main():
    """自动调度器主循环。

    循环逻辑：
    1. 读取上次处理到的最大 tweet ID
    2. 统计今日已创建的 analyze 任务数
    3. 查询 id > last_id 的新推文
    4. 如果发现新推文：
       a. 检查日预算是否已满（超过 DAILY_BUDGET 则跳过）
       b. 检查是否已有对应的 filter 任务（防重复）
       c. 创建新的 filter PipelineTask
    5. 提交事务 + 保存进度
    6. 等待 POLL_INTERVAL 秒后重复

    异常处理：
    - 查询/创建异常时执行 rollback，不会丢失已保存的进度
    - finally 中确保 session 关闭，避免连接泄漏
    """
    db.init_db()
    print(f"实时触发启动: 预算 {DAILY_BUDGET} 条/天, 轮询 {POLL_INTERVAL}s")

    while True:
        session = db.get_session()
        try:
            # 读取增量检查点
            last_id = get_last_checked_id()

            # 统计今日已创建的 analyze 任务数
            today_count = _count_today_analyze_tasks(session)

            # 查询增量新推文：id > last_id 且包含有效文本
            new_tweets = session.query(Tweet).filter(
                Tweet.id > last_id,
                Tweet.text != None,
                Tweet.text != "",
            ).order_by(Tweet.id).all()

            if new_tweets:
                print(f"  [{time.strftime('%H:%M:%S')}] 发现 {len(new_tweets)} 条新推文")

            # 逐条新推文处理
            for tweet in new_tweets:
                # 日预算检查：超过上限则跳过剩余
                if today_count >= DAILY_BUDGET:
                    print(f"  今日预算已满 ({DAILY_BUDGET})，跳过")
                    break

                # 去重检查：是否已存在该推文的 filter 任务
                # payload 中包含 tweet_id 的 JSON 字符串
                existing_f = session.query(PipelineTask).filter(
                    PipelineTask.task_type == "filter",
                    PipelineTask.payload.contains(str(tweet.id)),
                ).first()
                if existing_f:
                    continue

                # 创建 filter 任务：指定动作为 filter_single，传递 tweet.id
                t = PipelineTask(
                    task_type="filter",
                    status="pending",
                    payload=json.dumps(
                        {"action": "filter_single", "tweet_id": tweet.id},
                        ensure_ascii=False,
                    ),
                )
                session.add(t)
                today_count += 1

            if new_tweets:
                session.commit()
                # 更新检查点：记录最新处理的 tweet ID
                save_last_checked_id(new_tweets[-1].id)

        except Exception as e:
            print(f"  {e}")
            session.rollback()
        finally:
            session.close()

        time.sleep(POLL_INTERVAL)


def _count_today_analyze_tasks(session) -> int:
    """统计今日已创建的 analyze 任务数。

    用于日预算控制：当今日 analyze 任务数 >= DAILY_BUDGET 时，
    不再为新推文创建 filter 任务（filter 最终会触发 analyze）。
    这里统计 analyze（而非 filter），因为只有 analyze 才消耗 OpenAI API 费用。

    Args:
        session: SQLAlchemy 数据库会话对象

    Returns:
        int: 今天创建的 analyze 任务总数，查询失败时返回 0
    """
    today = time.strftime("%Y-%m-%d")
    from sqlalchemy import func
    return session.query(func.count(PipelineTask.id)).filter(
        PipelineTask.task_type == "analyze",
        PipelineTask.created_at >= today,
    ).scalar() or 0


if __name__ == "__main__":
    main()
