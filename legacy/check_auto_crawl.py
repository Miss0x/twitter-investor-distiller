"""检查全自动采集结果。"""
from __future__ import annotations

from pathlib import Path

from src.storage.database import db
from src.storage.models import Media, Tweet, User


def main() -> None:
    db.init_db()
    session = db.get_session()
    try:
        out: list[str] = []
        out.append(f"users={session.query(User).count()}")
        out.append(f"tweets={session.query(Tweet).count()}")
        out.append(f"media={session.query(Media).count()}")
        for username in ["TJ_Research", "dearbaibabybus"]:
            user = session.query(User).filter(User.username == username).one_or_none()
            if not user:
                out.append(f"\n@{username}: missing")
                continue
            tweets = (
                session.query(Tweet)
                .filter(Tweet.user_id == user.id)
                .order_by(Tweet.created_at_twitter.desc())
                .limit(5)
                .all()
            )
            out.append(f"\n@{username}: tweets={session.query(Tweet).filter(Tweet.user_id == user.id).count()}")
            for tweet in tweets:
                text = (tweet.text or "")[:160].replace("\n", " ")
                out.append(
                    f"{tweet.tweet_id}\t{tweet.created_at_twitter}\tvectorized={tweet.is_vectorized}\tsource={(tweet.extra_data or {}).get('source')}\t{text}"
                )

        target = Path("data/raw/auto_crawl_check.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(out), encoding="utf-8")
        print(target)
    finally:
        session.close()


if __name__ == "__main__":
    main()
