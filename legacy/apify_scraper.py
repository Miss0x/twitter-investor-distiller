"""Apify Twitter Scraper 集成（备选方案）。

需要先注册 Apify (https://apify.com) 并获取 API Token。
免费 tier 每月有 $5 compute credits，对于少量用户采集通常够用。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from src.crawler.twitter_scraper import ScrapedMedia, ScrapedTweet
from src.utils.env import load_project_env
from src.utils.logger import logger

load_project_env()

APIFY_BASE = "https://api.apify.com/v2"


class ApifyScraper:
    """通过 Apify 的 twitter-scraper actor 采集推文。"""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.getenv("APIFY_API_TOKEN")
        if not self.token:
            raise RuntimeError("缺少 APIFY_API_TOKEN，请注册 Apify 后获取")

    def fetch_user_timeline(self, username: str, max_items: int = 100) -> list[ScrapedTweet]:
        """调用 Apify actor 获取用户时间线。"""
        actor_id = "quacker/twitter-scraper"
        run_input = {
            "handles": [username],
            "tweetsDesired": max_items,
            "addUserInfo": True,
            "startUrls": [],
        }

        logger.info(f"Apify 开始采集 @{username}，目标 {max_items} 条")

        with httpx.Client(timeout=120) as client:
            # 启动 actor
            resp = client.post(
                f"{APIFY_BASE}/acts/{actor_id}/runs?token={self.token}",
                json=run_input,
            )
            resp.raise_for_status()
            run = resp.json()["data"]
            run_id = run["id"]
            logger.info(f"Apify run 已启动: {run_id}")

            # 等待完成（轮询）
            import time

            while True:
                time.sleep(5)
                status_resp = client.get(
                    f"{APIFY_BASE}/acts/{actor_id}/runs/{run_id}?token={self.token}"
                )
                status_resp.raise_for_status()
                status = status_resp.json()["data"]["status"]
                if status in ("SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"):
                    break
                logger.info(f"Apify run 状态: {status}")

            if status != "SUCCEEDED":
                raise RuntimeError(f"Apify run 失败: {status}")

            # 获取结果
            dataset_id = status_resp.json()["data"]["defaultDatasetId"]
            items_resp = client.get(
                f"{APIFY_BASE}/datasets/{dataset_id}/items?token={self.token}"
            )
            items_resp.raise_for_status()
            raw_items = items_resp.json()

        tweets: list[ScrapedTweet] = []
        for item in raw_items:
            parsed = self._parse_item(item, username)
            if parsed:
                tweets.append(parsed)

        logger.info(f"Apify 采集完成 @{username}: {len(tweets)} 条")
        return tweets

    def _parse_item(self, item: dict[str, Any], username: str) -> ScrapedTweet | None:
        try:
            tweet_id = str(item.get("id", ""))
            text = item.get("text", "")
            created_at = datetime.now()
            raw_time = item.get("createdAt")
            if raw_time:
                try:
                    created_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
                except Exception:
                    pass

            media: list[ScrapedMedia] = []
            for media_item in item.get("extendedEntities", {}).get("media", []):
                mtype = media_item.get("type", "photo")
                url = media_item.get("media_url_https", "")
                media.append(ScrapedMedia(media_type=mtype, url=url))

            return ScrapedTweet(
                tweet_id=tweet_id,
                username=username,
                text=text,
                created_at=created_at,
                url=f"https://x.com/{username}/status/{tweet_id}",
                like_count=item.get("favoriteCount", 0),
                retweet_count=item.get("retweetCount", 0),
                reply_count=item.get("replyCount", 0),
                is_reply=bool(item.get("inReplyToStatusId")),
                media=media,
                raw=item,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"解析 Apify 数据失败: {exc}")
            return None
