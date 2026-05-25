"""#3 实时触发 — Phase 4

DB 轮询新推文 → 自动入队 filter → analyze。
日预算控制，防 API 费用失控。

用法：python scripts/auto_scheduler.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from src.storage.database import db
from src.storage.models import Tweet, PipelineTask

DAILY_BUDGET = 20  # 每天最多自动创建 analyze 任务数
POLL_INTERVAL = 60  # 轮询间隔秒


def get_last_checked_id() -> int:
    """从状态文件读取上次检查到的 tweet id。"""
    state = Path("data/auto_scheduler_state.json")
    if state.exists():
        return json.loads(state.read_text()).get("last_id", 0)
    return 0


def save_last_checked_id(tweet_id: int) -> None:
    Path("data/auto_scheduler_state.json").write_text(
        json.dumps({"last_id": tweet_id, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}))


def main():
    db.init_db()
    print(f"🔄 实时触发启动: 预算 {DAILY_BUDGET} 条/天, 轮询 {POLL_INTERVAL}s")

    while True:
        session = db.get_session()
        try:
            last_id = get_last_checked_id()
            today_count = _count_today_analyze_tasks(session)

            new_tweets = session.query(Tweet).filter(
                Tweet.id > last_id, Tweet.text != None, Tweet.text != ""
            ).order_by(Tweet.id).all()

            if new_tweets:
                print(f"  [{time.strftime('%H:%M:%S')}] 发现 {len(new_tweets)} 条新推文")

            for tweet in new_tweets:
                if today_count >= DAILY_BUDGET:
                    print(f"  ⚠️ 今日预算已满 ({DAILY_BUDGET})，跳过")
                    break

                # 检查是否已有 filter 任务
                existing_f = session.query(PipelineTask).filter(
                    PipelineTask.task_type == "filter",
                    PipelineTask.payload.contains(str(tweet.id))
                ).first()
                if existing_f:
                    continue

                # 创建 filter 任务
                t = PipelineTask(
                    task_type="filter",
                    status="pending",
                    payload=json.dumps({"action": "filter_single", "tweet_id": tweet.id}, ensure_ascii=False)
                )
                session.add(t)
                today_count += 1

            if new_tweets:
                session.commit()
                save_last_checked_id(new_tweets[-1].id)

        except Exception as e:
            print(f"  ❌ {e}")
            session.rollback()
        finally:
            session.close()

        time.sleep(POLL_INTERVAL)


def _count_today_analyze_tasks(session) -> int:
    """统计今天创建的 analyze 任务数。"""
    today = time.strftime("%Y-%m-%d")
    from sqlalchemy import func
    return session.query(func.count(PipelineTask.id)).filter(
        PipelineTask.task_type == "analyze",
        PipelineTask.created_at >= today
    ).scalar() or 0


if __name__ == "__main__":
    main()
