"""Playwright 登录态 Twitter/X 采集器。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from src.crawler.twitter_scraper import ScrapedMedia, ScrapedTweet
from src.utils.env import load_project_env
from src.utils.logger import logger

load_project_env()

COOKIES_PATH = Path("data/cookies.json")


class PlaywrightScraper:
    """使用 Playwright + 登录态 Cookie 采集 Twitter/X。"""

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless

    def fetch_user_timeline(self, username: str, max_items: int = 100) -> list[ScrapedTweet]:
        """采集用户时间线。"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()

            if COOKIES_PATH.exists():
                cookies = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
                context.add_cookies(cookies)
                logger.info(f"已加载 {len(cookies)} 条 cookies")

            page = context.new_page()
            url = f"https://x.com/{username}"
            logger.info(f"Playwright 访问: {url}")
            page.goto(url, timeout=60000)
            page.wait_for_timeout(3000)

            # 检查是否被重定向到登录
            if "/login" in page.url:
                logger.error("Cookie 已失效，被重定向到登录页")
                browser.close()
                return []

            tweets: list[ScrapedTweet] = []
            last_height = 0
            scroll_attempts = 0
            max_scrolls = max(0, (max_items - 10) // 5)

            while len(tweets) < max_items and scroll_attempts < max_scrolls + 10:
                articles = page.query_selector_all("article[data-testid='tweet']")
                for article in articles[len(tweets) : max_items]:
                    parsed = self._parse_article(article, username)
                    if parsed and parsed.tweet_id not in {t.tweet_id for t in tweets}:
                        tweets.append(parsed)

                if len(tweets) >= max_items:
                    break

                page.evaluate("window.scrollBy(0, 800)")
                page.wait_for_timeout(1500)
                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    scroll_attempts += 1
                    if scroll_attempts >= 3:
                        break
                else:
                    scroll_attempts = 0
                    last_height = new_height

            # 保存更新的 cookies
            cookies = context.cookies()
            COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
            COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Cookie 已更新，共 {len(cookies)} 条")

            browser.close()
            logger.info(f"用户 @{username} Playwright 采集到 {len(tweets)} 条内容")
            return tweets

    def _parse_article(self, article: Any, username: str) -> ScrapedTweet | None:
        """解析单条推文。"""
        try:
            # 推文文本
            text_el = article.query_selector("[data-testid='tweetText']")
            text = text_el.inner_text() if text_el else ""

            # 时间戳链接（包含 tweet_id）
            time_link = article.query_selector("time")
            if not time_link:
                return None
            link_el = time_link.evaluate_handle("el => el.closest('a')")
            href = link_el.get_attribute("href") if link_el else ""
            tweet_id = href.rstrip("/").split("/")[-1] if href else ""
            tweet_url = f"https://x.com{href}" if href.startswith("/") else href

            # 发布时间
            datetime_str = time_link.get_attribute("datetime") or ""
            created_at = datetime.now()
            if datetime_str:
                try:
                    created_at = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            # 互动数据
            def get_count(testid: str) -> int:
                btn = article.query_selector(f"[data-testid='{testid}']")
                if btn:
                    txt = btn.inner_text()
                    # 处理 K/M 格式
                    txt = txt.strip().replace(",", "")
                    if txt.endswith("K"):
                        return int(float(txt[:-1]) * 1000)
                    if txt.endswith("M"):
                        return int(float(txt[:-1]) * 1000000)
                    if txt.isdigit():
                        return int(txt)
                return 0

            like_count = get_count("like")
            retweet_count = get_count("retweet")
            reply_count = get_count("reply")

            # 媒体
            media: list[ScrapedMedia] = []
            images = article.query_selector_all("[data-testid='tweetPhoto'] img")
            for img in images:
                src = img.get_attribute("src")
                if src:
                    media.append(ScrapedMedia(media_type="photo", url=src))

            videos = article.query_selector_all("[data-testid='videoPlayer']")
            for _ in videos:
                media.append(ScrapedMedia(media_type="video", url=""))

            # 是否回复
            is_reply = bool(article.query_selector("[data-testid='socialContext']"))

            return ScrapedTweet(
                tweet_id=tweet_id,
                username=username,
                text=text,
                created_at=created_at,
                url=tweet_url,
                like_count=like_count,
                retweet_count=retweet_count,
                reply_count=reply_count,
                is_reply=is_reply,
                media=media,
                raw={"source": "playwright"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"解析推文失败: {exc}")
            return None
