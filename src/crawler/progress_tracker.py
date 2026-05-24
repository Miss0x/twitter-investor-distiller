"""阶段 2/3：任务进度跟踪辅助。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.crawler.twitter_scraper import ScrapedTweet
from src.interfaces.job_service import CrawlJobService
from src.storage.database import db
from src.storage.models import CrawlJob, CrawlJobCheckpoint, CrawlJobStatus, Media, Tweet, User


@dataclass(slots=True)
class MockStepResult:
    """单次 mock 步进结果。"""

    username: str
    step_index: int
    total_steps: int
    tweets_collected_for_user: int
    tweets_collected_total: int
    users_completed: int
    last_seen_tweet_id: str


@dataclass(slots=True)
class PersistBatchResult:
    """单批次真实抓取持久化结果。"""

    inserted_count: int
    skipped_existing_count: int
    existing_updated_count: int
    tweets_collected_for_user: int
    tweets_collected_total: int
    last_seen_tweet_id: str | None
    last_seen_tweet_time: datetime | None


class ProgressTracker:
    """负责 checkpoint、进度和控制状态查询。"""

    def __init__(self, job_service: CrawlJobService | None = None) -> None:
        self.job_service = job_service or CrawlJobService()

    def get_job(self, job_id: int) -> CrawlJob:
        job = self.job_service.get_job(job_id)
        if job is None:
            raise ValueError(f"任务不存在: {job_id}")
        return job

    def get_checkpoint(self, job_id: int, username: str) -> CrawlJobCheckpoint | None:
        return self.job_service.get_checkpoint(job_id, username)

    def get_control_status(self, job_id: int) -> CrawlJobStatus:
        job = self.get_job(job_id)
        return CrawlJobStatus(job.status)

    def record_mock_step(
        self,
        job_id: int,
        *,
        username: str,
        step_index: int,
        total_steps: int,
        tweets_collected_for_user: int,
        tweets_collected_total: int,
        users_completed: int,
    ) -> MockStepResult:
        last_seen_tweet_id = f"mock-{username}-{step_index}"
        self.job_service.save_checkpoint(
            job_id,
            username,
            last_seen_tweet_id=last_seen_tweet_id,
            last_seen_tweet_time=datetime.now(),
            scroll_iterations=step_index,
            consecutive_no_new_items=0,
            tweets_collected=tweets_collected_for_user,
            page_cursor=str(step_index),
            stats_json={
                "mode": "mock",
                "step_index": step_index,
                "total_steps": total_steps,
                "tweets_collected_for_user": tweets_collected_for_user,
            },
        )

        job = self.get_job(job_id)
        total_users = max(job.users_total, 1)
        user_fraction = min(step_index / max(total_steps, 1), 1.0)
        progress_percent = ((users_completed + user_fraction) / total_users) * 100

        self.job_service.update_job_progress(
            job_id,
            current_username=username,
            progress_percent=progress_percent,
            tweets_collected_total=tweets_collected_total,
            users_completed=users_completed,
        )

        return MockStepResult(
            username=username,
            step_index=step_index,
            total_steps=total_steps,
            tweets_collected_for_user=tweets_collected_for_user,
            tweets_collected_total=tweets_collected_total,
            users_completed=users_completed,
            last_seen_tweet_id=last_seen_tweet_id,
        )

    def persist_scraped_tweets(
        self,
        job_id: int,
        *,
        username: str,
        tweets: list[ScrapedTweet],
        scroll_iterations: int,
        consecutive_no_new_items: int,
        users_completed: int,
        stats_json: dict | None = None,
    ) -> PersistBatchResult:
        session = db.get_session()
        inserted_count = 0
        skipped_existing_count = 0
        existing_updated_count = 0
        last_seen_tweet_id: str | None = None
        last_seen_tweet_time: datetime | None = None
        try:
            user = session.query(User).filter(User.username == username).one_or_none()
            if user is None:
                user = User(username=username, display_name=username)
                session.add(user)
                session.flush()

            for scraped in tweets:
                exists = session.query(Tweet).filter(Tweet.tweet_id == scraped.tweet_id).one_or_none()
                if exists:
                    # 更新已有的推文，补全引文/回复上下文
                    updated = False
                    for field in ['is_reply', 'is_retweet', 'is_quote',
                                  'replied_to_user', 'replied_to_tweet_id', 'replied_text',
                                  'quoted_tweet_id', 'quoted_user', 'quoted_text']:
                        old_val = getattr(exists, field)
                        new_val = getattr(scraped, field)
                        if new_val and not old_val:
                            setattr(exists, field, new_val)
                            updated = True
                    if updated:
                        existing_updated_count += 1
                    else:
                        skipped_existing_count += 1
                    continue

                tweet = Tweet(
                    tweet_id=scraped.tweet_id,
                    user_id=user.id,
                    text=scraped.text or "",
                    created_at_twitter=scraped.created_at,
                    like_count=scraped.like_count,
                    retweet_count=scraped.retweet_count,
                    reply_count=scraped.reply_count,
                    quote_count=scraped.quote_count,
                    view_count=scraped.view_count,
                    is_reply=scraped.is_reply,
                    is_retweet=scraped.is_retweet,
                    is_quote=scraped.is_quote,
                    replied_to_tweet_id=scraped.replied_to_tweet_id,
                    replied_to_user=scraped.replied_to_user,
                    replied_text=scraped.replied_text,
                    quoted_tweet_id=scraped.quoted_tweet_id,
                    quoted_user=scraped.quoted_user,
                    quoted_text=scraped.quoted_text,
                    has_media=bool(scraped.media),
                    media_count=len(scraped.media),
                    url=scraped.url,
                    extra_data=scraped.raw,
                )
                session.add(tweet)
                session.flush()

                for media_item in scraped.media:
                    session.add(
                        Media(
                            tweet_id=tweet.id,
                            media_type=media_item.media_type,
                            media_url=media_item.url,
                            width=media_item.width,
                            height=media_item.height,
                            duration=media_item.duration,
                            downloaded=False,
                        )
                    )

                inserted_count += 1
                last_seen_tweet_id = scraped.tweet_id
                last_seen_tweet_time = scraped.created_at

            session.commit()
        finally:
            session.close()

        job = self.get_job(job_id)
        checkpoint = self.get_checkpoint(job_id, username)
        tweets_collected_for_user = (checkpoint.tweets_collected if checkpoint else 0) + inserted_count
        tweets_collected_total = job.tweets_collected_total + inserted_count
        total_users = max(job.users_total, 1)
        base_progress = (users_completed / total_users) * 100
        progress_percent = min(base_progress + (inserted_count / max(1, total_users * 20)) * 100, 99.0)

        self.job_service.save_checkpoint(
            job_id,
            username,
            last_seen_tweet_id=last_seen_tweet_id,
            last_seen_tweet_time=last_seen_tweet_time,
            scroll_iterations=scroll_iterations,
            consecutive_no_new_items=consecutive_no_new_items,
            tweets_collected=tweets_collected_for_user,
            stats_json=stats_json,
        )
        self.job_service.update_job_progress(
            job_id,
            current_username=username,
            progress_percent=progress_percent,
            tweets_collected_total=tweets_collected_total,
            users_completed=users_completed,
        )

        return PersistBatchResult(
            inserted_count=inserted_count,
            skipped_existing_count=skipped_existing_count,
            existing_updated_count=existing_updated_count,
            tweets_collected_for_user=tweets_collected_for_user,
            tweets_collected_total=tweets_collected_total,
            last_seen_tweet_id=last_seen_tweet_id,
            last_seen_tweet_time=last_seen_tweet_time,
        )

    def mark_user_completed(
        self,
        job_id: int,
        *,
        username: str,
        tweets_collected_total: int,
        users_completed: int,
    ) -> CrawlJob:
        job = self.get_job(job_id)
        usernames = job.target_usernames or []
        next_username = usernames[users_completed] if users_completed < len(usernames) else None
        progress_percent = (users_completed / max(job.users_total, 1)) * 100
        return self.job_service.update_job_progress(
            job_id,
            current_username=next_username,
            progress_percent=progress_percent,
            tweets_collected_total=tweets_collected_total,
            users_completed=users_completed,
        )
