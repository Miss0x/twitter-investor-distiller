"""投资风格蒸馏模块。"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from src.storage.models import Tweet, User


class StyleDistiller:
    """从历史内容中提取用户风格画像。"""

    def build_basic_profile(self, session: Session, username: str) -> dict:
        user = session.query(User).filter(User.username == username.lstrip("@")).one_or_none()
        if not user:
            return {"error": "user not found"}

        tweets = session.query(Tweet).filter(Tweet.user_id == user.id).all()
        total = len(tweets)
        reply_count = sum(1 for t in tweets if t.is_reply)
        media_count = sum(1 for t in tweets if t.has_media)
        avg_length = sum(len(t.text or "") for t in tweets) / total if total else 0

        return {
            "username": user.username,
            "display_name": user.display_name,
            "description": user.description,
            "tweet_count": total,
            "reply_ratio": reply_count / total if total else 0,
            "media_ratio": media_count / total if total else 0,
            "avg_text_length": avg_length,
        }
