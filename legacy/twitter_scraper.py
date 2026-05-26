"""Twitter/X 统一数据结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ScrapedMedia:
    """采集到的媒体信息。"""

    media_type: str
    url: str
    width: int | None = None
    height: int | None = None
    duration: int | None = None


@dataclass(slots=True)
class ScrapedTweet:
    """采集到的推文信息。"""

    tweet_id: str
    username: str
    text: str
    created_at: datetime
    url: str
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    view_count: int = 0
    is_reply: bool = False

    is_retweet: bool = False
    is_quote: bool = False
    replied_to_user: str | None = None
    replied_to_tweet_id: str | None = None
    replied_text: str | None = None
    quoted_tweet_id: str | None = None
    quoted_user: str | None = None
    quoted_text: str | None = None
    media: list[ScrapedMedia] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
