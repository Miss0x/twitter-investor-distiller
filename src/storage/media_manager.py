"""媒体文件管理模块。"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from src.crawler.media_downloader import MediaDownloader
from src.storage.models import Media, Tweet
from src.utils.logger import logger


class MediaManager:
    """批量下载数据库中未下载的媒体。"""

    def __init__(self, downloader: MediaDownloader | None = None) -> None:
        self.downloader = downloader or MediaDownloader()

    def download_pending(self, session: Session, limit: int = 100) -> int:
        media_items = (
            session.query(Media)
            .filter(Media.downloaded.is_(False))
            .limit(limit)
            .all()
        )
        count = 0
        for index, media in enumerate(media_items):
            tweet = session.query(Tweet).filter(Tweet.id == media.tweet_id).one()
            username = tweet.user.username
            path = self.downloader.download(media.media_url, username, tweet.tweet_id, index)
            if path:
                media.local_path = str(path)
                media.downloaded = True
                count += 1
            else:
                media.download_error = "download failed"
        session.commit()
        logger.info(f"媒体批量下载完成: {count}/{len(media_items)}")
        return count
