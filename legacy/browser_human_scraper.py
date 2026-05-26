"""阶段 3：基于 Playwright + cookies 的真人化浏览器抓取器。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import Browser, Page, sync_playwright

from src.crawler.human_behavior import HumanBehaviorController, HumanBehaviorProfile
from src.crawler.twitter_scraper import ScrapedMedia, ScrapedTweet
from src.storage.models import CrawlJobCheckpoint
from src.utils.logger import logger

COOKIES_PATH = Path("data/cookies.json")


def _normalize_cookies(raw_cookies: list[dict]) -> list[dict]:
    """将浏览器导出的 cookies 字段标准化为 Playwright 兼容格式。"""
    normalized = []
    for c in raw_cookies:
        item = {
            "name": c["name"],
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
        }
        if c.get("httpOnly"):
            item["httpOnly"] = True
        if c.get("secure"):
            item["secure"] = True
        same_site = c.get("sameSite")
        if same_site is None or same_site == "no_restriction":
            item["sameSite"] = "None"
        elif same_site.lower() == "lax":
            item["sameSite"] = "Lax"
        elif same_site.lower() == "strict":
            item["sameSite"] = "Strict"
        else:
            item["sameSite"] = "None"
        if c.get("expirationDate"):
            item["expires"] = c["expirationDate"]
        normalized.append(item)
    return normalized


@dataclass(slots=True)
class BrowserBatchResult:
    """单轮浏览器扫描结果。"""

    tweets: list[ScrapedTweet]
    scroll_iterations: int
    consecutive_no_new_items: int
    reached_time_limit: bool
    oldest_tweet_time: datetime | None


class BrowserHumanScraper:
    """真人化浏览器抓取器。"""

    def __init__(
        self,
        *,
        headless: bool = True,
        cookies_path: str | Path = COOKIES_PATH,
        timeout_ms: int = 120000,
        max_scroll_rounds: int = 160,
        no_new_items_limit: int = 10,
        recent_days: int = 90,
        minimum_created_at: datetime | None = None,
        page_ready_timeout_seconds: int = 120,
        settle_after_scroll_ms: int = 2500,
        behavior_profile: HumanBehaviorProfile | None = None,
    ) -> None:
        self.headless = headless
        self.cookies_path = Path(cookies_path)
        self.timeout_ms = timeout_ms
        self.max_scroll_rounds = max_scroll_rounds
        self.no_new_items_limit = no_new_items_limit
        self.recent_days = recent_days
        self.minimum_created_at = minimum_created_at
        self.page_ready_timeout_seconds = page_ready_timeout_seconds
        self.settle_after_scroll_ms = settle_after_scroll_ms
        self.behavior = HumanBehaviorController(behavior_profile)

    def crawl_user_recent(
        self,
        username: str,
        checkpoint: CrawlJobCheckpoint | None = None,
    ) -> BrowserBatchResult:
        username = username.lstrip("@").strip()
        if not username:
            raise ValueError("username 不能为空")
        if not self.cookies_path.exists():
            raise FileNotFoundError(f"未找到 cookies 文件: {self.cookies_path}")

        threshold = self.minimum_created_at or (datetime.now() - timedelta(days=self.recent_days))
        known_ids = {checkpoint.last_seen_tweet_id} if checkpoint and checkpoint.last_seen_tweet_id else set()
        scroll_iterations = checkpoint.scroll_iterations if checkpoint else 0
        consecutive_no_new_items = checkpoint.consecutive_no_new_items if checkpoint else 0
        tweets: list[ScrapedTweet] = []
        oldest_tweet_time: datetime | None = None
        reached_time_limit = False

        with sync_playwright() as p:
            browser: Browser | None = None
            try:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )
                context = browser.new_context(
                    viewport={"width": 1365, "height": 900},
                    locale="zh-CN",
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                context.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                    """
                )
                raw_cookies = json.loads(self.cookies_path.read_text(encoding="utf-8"))
                cookies = _normalize_cookies(raw_cookies)
                context.add_cookies(cookies)
                page = context.new_page()
                self._open_profile(page, username)

                while scroll_iterations < self.max_scroll_rounds:
                    self.behavior.maybe_expand_text(page)
                    new_items, batch_oldest_time = self._extract_visible_tweets(page, username, threshold, known_ids)
                    if batch_oldest_time and (oldest_tweet_time is None or batch_oldest_time < oldest_tweet_time):
                        oldest_tweet_time = batch_oldest_time
                    if new_items:
                        tweets.extend(new_items)
                        consecutive_no_new_items = 0
                    else:
                        consecutive_no_new_items += 1

                    if oldest_tweet_time and oldest_tweet_time <= threshold:
                        reached_time_limit = True
                        break

                    if consecutive_no_new_items >= self.no_new_items_limit:
                        page.wait_for_timeout(self.settle_after_scroll_ms * 3)
                        refreshed_items, refreshed_oldest_time = self._extract_visible_tweets(page, username, threshold, known_ids)
                        if refreshed_oldest_time and (oldest_tweet_time is None or refreshed_oldest_time < oldest_tweet_time):
                            oldest_tweet_time = refreshed_oldest_time
                        if refreshed_items:
                            tweets.extend(refreshed_items)
                            consecutive_no_new_items = 0
                            continue
                        logger.info(f"@{username} 连续 {self.no_new_items_limit} 轮未发现新内容，结束本批次抓取")
                        break

                    self.behavior.scroll_timeline(page)
                    self.behavior.micro_backtrack(page)
                    page.wait_for_timeout(self.settle_after_scroll_ms)
                    scroll_iterations += 1

                    new_items_after_scroll, batch_oldest_time_after_scroll = self._extract_visible_tweets(page, username, threshold, known_ids)
                    if batch_oldest_time_after_scroll and (oldest_tweet_time is None or batch_oldest_time_after_scroll < oldest_tweet_time):
                        oldest_tweet_time = batch_oldest_time_after_scroll
                    if new_items_after_scroll:
                        tweets.extend(new_items_after_scroll)
                        consecutive_no_new_items = 0
                    else:
                        consecutive_no_new_items += 1

                    if oldest_tweet_time and oldest_tweet_time <= threshold:
                        reached_time_limit = True
                        break

                context.close()
            finally:
                if browser:
                    browser.close()

        logger.info(
            f"浏览器抓取结束 @{username}: tweets={len(tweets)}, "
            f"scroll_iterations={scroll_iterations}, no_new={consecutive_no_new_items}, "
            f"reached_time_limit={reached_time_limit}"
        )
        return BrowserBatchResult(
            tweets=tweets,
            scroll_iterations=scroll_iterations,
            consecutive_no_new_items=consecutive_no_new_items,
            reached_time_limit=reached_time_limit,
            oldest_tweet_time=oldest_tweet_time,
        )

    def crawl_user_search_window(
        self,
        username: str,
        since: datetime,
        until: datetime,
    ) -> BrowserBatchResult:
        """按日期窗口搜索用户推文：from:USER since:DATE until:DATE。"""
        username = username.lstrip("@").strip()
        if not username:
            raise ValueError("username 不能为空")
        if not self.cookies_path.exists():
            raise FileNotFoundError(f"未找到 cookies 文件: {self.cookies_path}")

        since_str = since.strftime("%Y-%m-%d")
        until_str = until.strftime("%Y-%m-%d")
        query = f"from:{username} since:{since_str} until:{until_str}"
        search_url = f"https://x.com/search?q={quote(query)}&src=typed_query&f=live"

        threshold = since.replace(hour=0, minute=0, second=0, microsecond=0)
        known_ids: set[str] = set()
        scroll_iterations = 0
        consecutive_no_new_items = 0
        tweets: list[ScrapedTweet] = []
        oldest_tweet_time: datetime | None = None
        reached_time_limit = False

        with sync_playwright() as p:
            browser: Browser | None = None
            try:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                )
                context = browser.new_context(
                    viewport={"width": 1365, "height": 900},
                    locale="zh-CN",
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                context.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                    """
                )
                raw_cookies = json.loads(self.cookies_path.read_text(encoding="utf-8"))
                cookies = _normalize_cookies(raw_cookies)
                context.add_cookies(cookies)
                page = context.new_page()
                self._open_search(page, username, search_url, since_str, until_str)

                while scroll_iterations < self.max_scroll_rounds:
                    self.behavior.maybe_expand_text(page)
                    new_items, batch_oldest_time = self._extract_visible_tweets(page, username, threshold, known_ids)
                    if batch_oldest_time and (oldest_tweet_time is None or batch_oldest_time < oldest_tweet_time):
                        oldest_tweet_time = batch_oldest_time
                    if new_items:
                        tweets.extend(new_items)
                        consecutive_no_new_items = 0
                    else:
                        consecutive_no_new_items += 1

                    if oldest_tweet_time and oldest_tweet_time <= threshold:
                        reached_time_limit = True
                        break

                    if consecutive_no_new_items >= self.no_new_items_limit:
                        page.wait_for_timeout(self.settle_after_scroll_ms * 3)
                        refreshed_items, refreshed_oldest_time = self._extract_visible_tweets(page, username, threshold, known_ids)
                        if refreshed_oldest_time and (oldest_tweet_time is None or refreshed_oldest_time < oldest_tweet_time):
                            oldest_tweet_time = refreshed_oldest_time
                        if refreshed_items:
                            tweets.extend(refreshed_items)
                            consecutive_no_new_items = 0
                            continue
                        logger.info(f"@{username} [{since_str}~{until_str}] 连续 {self.no_new_items_limit} 轮无新内容，结束本窗口")
                        break

                    self.behavior.scroll_timeline(page)
                    self.behavior.micro_backtrack(page)
                    page.wait_for_timeout(self.settle_after_scroll_ms)
                    scroll_iterations += 1

                    new_items_after_scroll, batch_oldest_time_after_scroll = self._extract_visible_tweets(page, username, threshold, known_ids)
                    if batch_oldest_time_after_scroll and (oldest_tweet_time is None or batch_oldest_time_after_scroll < oldest_tweet_time):
                        oldest_tweet_time = batch_oldest_time_after_scroll
                    if new_items_after_scroll:
                        tweets.extend(new_items_after_scroll)
                        consecutive_no_new_items = 0
                    else:
                        consecutive_no_new_items += 1

                    if oldest_tweet_time and oldest_tweet_time <= threshold:
                        reached_time_limit = True
                        break

                context.close()
            finally:
                if browser:
                    browser.close()

        logger.info(
            f"搜索窗口抓取结束 @{username} [{since_str}~{until_str}]: tweets={len(tweets)}, "
            f"scroll_iterations={scroll_iterations}, reached_time_limit={reached_time_limit}"
        )
        return BrowserBatchResult(
            tweets=tweets,
            scroll_iterations=scroll_iterations,
            consecutive_no_new_items=consecutive_no_new_items,
            reached_time_limit=reached_time_limit,
            oldest_tweet_time=oldest_tweet_time,
        )

    def _open_profile(self, page: Page, username: str) -> None:
        url = f"https://x.com/{username}/with_replies"
        logger.info(f"打开用户主页: {url}")
        page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
        if "/login" in page.url:
            raise RuntimeError("cookies 已失效，页面被重定向到登录页")

        import time as _time
        deadline = _time.time() + self.page_ready_timeout_seconds
        articles_found = False
        timeline_found = False
        while _time.time() < deadline:
            article_count = len(page.query_selector_all("article[data-testid='tweet']"))
            if article_count > 0:
                articles_found = True
                break
            if len(page.query_selector_all("article")) > 0:
                timeline_found = True
            page.wait_for_timeout(800)
        if articles_found:
            logger.info(f"@{username} 时间线已渲染")
            self.behavior.stabilize_after_navigation(page)
        elif timeline_found:
            logger.warning(f"@{username} 找到 article 但未识别 tweet card，继续等待滚动加载")
        else:
            logger.warning(f"{self.page_ready_timeout_seconds}s 内未找到 tweet article，@{username} 页面可能为空或被限流")

    def _open_search(self, page: Page, username: str, search_url: str, since_str: str, until_str: str) -> None:
        logger.info(f"打开搜索页 @{username} [{since_str}~{until_str}]: {search_url}")
        page.goto(search_url, timeout=self.timeout_ms, wait_until="domcontentloaded")
        if "/login" in page.url:
            raise RuntimeError("cookies 已失效，页面被重定向到登录页")

        import time as _time
        deadline = _time.time() + self.page_ready_timeout_seconds
        articles_found = False
        while _time.time() < deadline:
            article_count = len(page.query_selector_all("article[data-testid='tweet']"))
            if article_count > 0:
                articles_found = True
                break
            page.wait_for_timeout(800)
        if articles_found:
            logger.info(f"@{username} [{since_str}~{until_str}] 搜索结果已渲染")
            self.behavior.stabilize_after_navigation(page)
        else:
            logger.warning(f"@{username} [{since_str}~{until_str}] {self.page_ready_timeout_seconds}s 内未找到搜索结果")

    def _extract_visible_tweets(
        self,
        page: Page,
        username: str,
        threshold: datetime,
        known_ids: set[str],
    ) -> tuple[list[ScrapedTweet], datetime | None]:
        articles = page.query_selector_all("article[data-testid='tweet']")
        tweets: list[ScrapedTweet] = []
        oldest_tweet_time: datetime | None = None
        for article in articles:
            parsed = self._parse_article(article, username)
            if parsed is None:
                continue
            if parsed.tweet_id in known_ids:
                continue
            known_ids.add(parsed.tweet_id)
            tweets.append(parsed)
            if oldest_tweet_time is None or parsed.created_at < oldest_tweet_time:
                oldest_tweet_time = parsed.created_at
            if parsed.created_at < threshold:
                break
        return tweets, oldest_tweet_time

    def _parse_article(self, article, username: str) -> ScrapedTweet | None:
        try:
            text_el = article.query_selector("[data-testid='tweetText']")
            text = text_el.inner_text().strip() if text_el else ""

            time_el = article.query_selector("time")
            if not time_el:
                return None
            href = time_el.evaluate("el => el.closest('a')?.getAttribute('href') || ''")
            if not href:
                return None
            tweet_id = href.rstrip("/").split("/")[-1]
            tweet_url = f"https://x.com{href}" if href.startswith("/") else href

            datetime_str = time_el.get_attribute("datetime") or ""
            created_at = datetime.now()
            if datetime_str:
                created_at = datetime.fromisoformat(datetime_str.replace("Z", "+00:00")).replace(tzinfo=None)

            # --- 回复信息 ---
            is_reply = False
            replied_to_user: str | None = None
            replied_to_tweet_id: str | None = None
            replied_text: str | None = None

            social_ctx = article.query_selector("[data-testid='socialContext']")
            if social_ctx:
                ctx_text = social_ctx.inner_text().strip()
                if "回复" in ctx_text:
                    is_reply = True
                    parts = ctx_text.split("@")
                    if len(parts) > 1:
                        replied_to_user = parts[-1].strip()
                elif "转推" in ctx_text or "Reposted" in ctx_text:
                    pass  # retweet by someone else, not our user

            # --- 引用信息 ---
            is_quote = False
            quoted_tweet_id: str | None = None
            quoted_user: str | None = None
            quoted_text: str | None = None

            quote_card = article.query_selector("div[role='link'][tabindex='0']")
            if quote_card:
                is_quote = True
                quote_inner = quote_card.inner_text().strip()
                # Parse: "UserName\n@userhandle\n·\ndate\ntweet text"
                lines = [l.strip() for l in quote_inner.split("\n") if l.strip()]
                if lines:
                    quoted_user = lines[0]
                    for line in lines[1:3]:
                        if line.startswith("@"):
                            quoted_user = line.lstrip("@")  # normalize to bare handle
                    # The tweet text: skip display name, @handle, date/metadata lines
                    text_start = 0
                    for j, line in enumerate(lines):
                        if line.startswith("@"):
                            text_start = j + 1
                        if ("年" in line or "月" in line) and any(c.isdigit() for c in line):
                            text_start = max(text_start, j + 1)
                        if line.startswith("回复 ") or line.startswith("Replying to"):
                            text_start = max(text_start, j + 1)
                    if text_start > 0 and text_start < len(lines):
                        quoted_text = "\n".join(lines[text_start:])

                # Get quoted tweet link from ANY link in the quote card
                for a_tag in quote_card.query_selector_all("a"):
                    ahref = a_tag.get_attribute("href") or ""
                    if "/status/" in ahref and ahref.count("/status/") == 1:
                        # Avoid /status/xxx/photo/1, /status/xxx/analytics
                        path = ahref.split("?")[0]
                        parts = path.strip("/").split("/")
                        if "status" in parts:
                            idx = parts.index("status")
                            if idx + 1 < len(parts):
                                quoted_tweet_id = parts[idx + 1]
                        break

            # --- 从引用文本中派生回复信息 ---
            # X.com 将回复表现为引用推文，"回复 @username" 在 quote 卡片原文里
            if not is_reply and quote_card and ("回复 " in quote_inner or "Replying to" in quote_inner):
                is_reply = True
                replied_text = quoted_text
                replied_to_tweet_id = quoted_tweet_id
                # Extract username from "回复 @username" pattern
                for prefix in ["回复 @", "Replying to @"]:
                    if prefix in quote_inner:
                        after = quote_inner.split(prefix, 1)[1]
                        replied_to_user = after.split()[0].split("\n")[0].rstrip(".")
                        break

            # --- 转推检测 ---
            is_retweet = False
            if social_ctx:
                ctx_text = social_ctx.inner_text().strip()
                if "转推" in ctx_text or "Reposted" in ctx_text:
                    # The current user retweeted someone
                    is_retweet = True

            # --- 媒体 ---
            media: list[ScrapedMedia] = []
            for img in article.query_selector_all("[data-testid='tweetPhoto'] img"):
                src = img.get_attribute("src")
                if src:
                    media.append(ScrapedMedia(media_type="photo", url=src))

            return ScrapedTweet(
                tweet_id=tweet_id,
                username=username,
                text=text,
                created_at=created_at,
                url=tweet_url,
                is_reply=is_reply,
                is_retweet=is_retweet,
                is_quote=is_quote,
                replied_to_user=replied_to_user,
                replied_to_tweet_id=replied_to_tweet_id,
                replied_text=replied_text,
                quoted_tweet_id=quoted_tweet_id,
                quoted_user=quoted_user,
                quoted_text=quoted_text,
                media=media,
                raw={"source": "browser_human"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"解析 article 失败: {exc}")
            return None
