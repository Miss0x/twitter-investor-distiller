"""Daemon 守护进程 — 独立脚本, 由 web_api.py 通过 subprocess 启动。

轮转拉取监控用户的推文, 自动触发 filter→analyze 流水线。
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.crawler.twitterapi_fetcher import TwitterAPIFetcher
from src.storage.database import db
from src.storage.models import PipelineTask


def run():
    db.init_db()
    USERS = _load_users()
    INTERVAL = 120
    fetcher = TwitterAPIFetcher()
    state = Path("data/auto_scheduler_state.json")
    st = json.loads(state.read_text()) if state.exists() else {}
    idx = st.get("user_idx", 0)

    while True:
        try:
            USERS = _load_users() or USERS  # 每次循环重读, 支持动态添加
            username = USERS[idx % len(USERS)]
            st["user_idx"] = (idx + 1) % len(USERS)
            st["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")

            last_ts = fetcher.get_last_tweet_ts(username)
            db_cnt = fetcher.get_user_tweet_count(username)
            st[f"db_count_{username}"] = db_cnt

            res = fetcher.fetch_tweets(username, max_pages=1, since_ts=last_ts)
            new_cnt = res.get("total_new", 0)
            if res.get("ok") and new_cnt > 0:
                st["total_fetched"] = st.get("total_fetched", 0) + new_cnt
                session = db.get_session()
                for _ in range(new_cnt):
                    t = PipelineTask(
                        task_type="filter",
                        status="pending",
                        payload=json.dumps({"action": "filter_latest", "user": username}),
                    )
                    session.add(t)
                session.commit()
                session.close()
                print(f"[DAEMON] {username}: +{new_cnt} tweets, pipeline triggered")
            elif new_cnt == 0 and res.get("ok"):
                print(f"[DAEMON] {username}: 无新推文")
            else:
                print(f"[DAEMON] {username}: {res.get('error', '')}")

            state.write_text(json.dumps(st, ensure_ascii=False))
            idx += 1
            time.sleep(INTERVAL)
        except Exception as exc:
            print(f"[DAEMON] error: {exc}")
            time.sleep(INTERVAL * 2)


def _load_users():
    fp = Path("data/users.json")
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    return ["TJ_Research", "dearbaibabybus"]


if __name__ == "__main__":
    run()
