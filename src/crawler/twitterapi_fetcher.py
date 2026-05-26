"""twitterapi.io 数据抓取器 —— 替代浏览器爬虫作为主路径。

通过第三方 API 安全拉取推文和用户资料，写 SQLite。
支持 cursor 翻页、增量抓取、去重。
"""
from __future__ import annotations

import json
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Any

from src.storage.database import db
from src.storage.models import Tweet, User
from src.config import config

API_BASE = "https://api.twitterapi.io"


def _headers():
    key = config.twitterapi_key
    if not key:
        raise RuntimeError("TWITTERAPI_KEY 未在 .env 中设置")
    return {"X-API-Key": key}


class TwitterAPIFetcher:
    """通过 twitterapi.io 拉取推文和用户数据。"""

    def __init__(self):
        db.init_db()

    def _get(self, endpoint: str, params: dict = None) -> dict:
        r = requests.get(f"{API_BASE}{endpoint}", headers=_headers(), params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def fetch_user_info(self, username: str) -> dict:
        data = self._get("/twitter/user/info", {"userName": username})
        user_data = data.get("data", {})
        if not user_data:
            return {"ok": False, "error": data.get("message", "unknown")}

        session = db.get_session()
        try:
            existing = session.query(User).filter(User.username == username).first()
            if existing:
                existing.display_name = user_data.get("name")
                existing.followers_count = user_data.get("followers", 0)
                existing.following_count = user_data.get("following", 0)
                existing.description = user_data.get("description")
                existing.tweet_count = user_data.get("statusesCount", 0)
                existing.profile_image_url = user_data.get("profilePicture")
                existing.updated_at = datetime.now()
            else:
                u = User(
                    username=username,
                    display_name=user_data.get("name"),
                    followers_count=user_data.get("followers", 0),
                    following_count=user_data.get("following", 0),
                    description=user_data.get("description"),
                    tweet_count=user_data.get("statusesCount", 0),
                    profile_image_url=user_data.get("profilePicture"),
                )
                session.add(u)
            session.commit()
            return {"ok": True, "followers": user_data.get("followers")}
        except Exception as e:
            session.rollback()
            return {"ok": False, "error": str(e)}
        finally:
            session.close()

    def get_last_tweet_ts(self, username: str) -> int:
        session = db.get_session()
        try:
            last = session.query(Tweet).filter(
                Tweet.user.has(username=username)
            ).order_by(Tweet.created_at_twitter.desc()).first()
            if last and last.created_at_twitter:
                return int(last.created_at_twitter.timestamp()) + 1
            return 0
        except Exception:
            return 0
        finally:
            session.close()

    def get_user_tweet_count(self, username: str) -> int:
        session = db.get_session()
        try:
            return session.query(Tweet).join(User).filter(User.username == username).count()
        except Exception:
            return 0
        finally:
            session.close()

    def fetch_tweets(self, username: str, max_pages: int = 50, cursor: str = "",
                     since_ts: int = 0, until_ts: int = 0) -> dict:
        total_new = 0
        pages = 0

        query_parts = [f"from:{username}"]
        if since_ts > 0:
            query_parts.append(f"since_time:{since_ts}")
        if until_ts > 0:
            query_parts.append(f"until_time:{until_ts}")
        base_query = " ".join(query_parts)

        for page in range(max_pages):
            params = {"query": base_query, "queryType": "Latest"}
            if cursor:
                params["cursor"] = cursor

            try:
                data = self._get("/twitter/tweet/advanced_search", params)
            except Exception as e:
                return {"ok": False, "error": str(e), "pages": pages, "total_new": total_new, "cursor": cursor}

            tweets = data.get("tweets", [])
            saved = self._save_tweets(username, tweets)
            total_new += saved
            pages += 1

            if not data.get("has_next_page"):
                break
            cursor = data.get("next_cursor", "")
            if not cursor:
                break

        return {"ok": True, "pages": pages, "total_new": total_new, "cursor": cursor}

    def _save_tweets(self, username: str, api_tweets: list[dict]) -> int:
        session = db.get_session()
        saved = 0
        try:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                user = User(username=username, display_name=username)
                session.add(user)
                session.flush()

            for t in api_tweets:
                tw_id = t.get("id")
                if not tw_id:
                    continue
                if session.query(Tweet).filter(Tweet.tweet_id == tw_id).first():
                    continue

                qt = t.get("quoted_tweet")
                rt = t.get("retweeted_tweet")
                created = _parse_twitter_time(t.get("createdAt", ""))

                tw = Tweet(
                    tweet_id=tw_id,
                    user_id=user.id,
                    text=t.get("text", ""),
                    created_at_twitter=created,
                    is_reply=t.get("isReply", False),
                    is_retweet=rt is not None,
                    is_quote=qt is not None,
                    replied_to_tweet_id=t.get("inReplyToId"),
                    replied_to_user=t.get("inReplyToUsername"),
                    quoted_tweet_id=qt.get("id") if qt else None,
                    quoted_user=qt.get("author", {}).get("userName") if qt else None,
                    quoted_text=qt.get("text") if qt else None,
                    like_count=t.get("likeCount", 0),
                    retweet_count=t.get("retweetCount", 0),
                    reply_count=t.get("replyCount", 0),
                    quote_count=t.get("quoteCount", 0),
                    view_count=t.get("viewCount", 0),
                    url=t.get("url", ""),
                    extra_data={
                        "bookmark_count": t.get("bookmarkCount", 0),
                        "lang": t.get("lang", ""),
                        "source": t.get("source", ""),
                        "conversation_id": t.get("conversationId"),
                    },
                )
                session.add(tw)
                saved += 1

            session.commit()
            return saved
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _parse_twitter_time(s: str) -> datetime:
    if not s:
        return datetime.now()
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        return datetime.now()
