"""
媒体文件管理模块

负责批量下载推文中关联的媒体文件（图片/GIF/视频）。
通过 MediaManager 类统一管理下载流程：查询未下载的媒体记录 → 逐个下载 → 更新数据库状态。
与 MediaDownloader 协作完成实际的文件下载，与数据库模型 Media/Tweet 协作完成状态持久化。
"""
from __future__ import annotations


from sqlalchemy.orm import Session

from src.crawler.media_downloader import MediaDownloader
from src.storage.models import Media, Tweet
from src.utils.logger import logger


class MediaManager:
    """
    媒体文件批量下载管理器

    负责从数据库中查询尚未下载的媒体记录，调用下载器逐一下载，
    并将下载结果（本地路径或错误信息）写回数据库。

    Attributes:
        downloader: MediaDownloader 实例，负责实际的 HTTP 下载和文件存储
    """

    def __init__(self, downloader: MediaDownloader | None = None) -> None:
        """
        Args:
            downloader: 可选的 MediaDownloader 实例。若未提供则自动创建一个默认实例。
                       支持依赖注入，便于测试时替换为 mock 对象。
        """
        self.downloader = downloader or MediaDownloader()

    def download_pending(self, session: Session, limit: int = 100) -> int:
        """
        下载所有待处理的媒体文件

        查询数据库中 downloaded=False 的媒体记录，逐一下载并更新状态。
        每批最多处理 limit 条记录，处理完毕后统一提交事务。

        Args:
            session: SQLAlchemy 数据库会话，用于查询和更新媒体状态
            limit: 单次最多处理的媒体数量，防止一次性下载过多文件

        Returns:
            int: 本轮成功下载的媒体文件数量

        Note:
            - 每条媒体记录通过其关联的 Tweet → User 查找用户名，用于构建本地存储路径
            - 下载失败不会中断流程，会在 media.download_error 中记录错误信息
            - 所有记录处理完后统一 commit，减少数据库 IO
        """
        # 查询所有未下载的媒体记录，按 limit 限制数量
        media_items = (
            session.query(Media)
            .filter(Media.downloaded.is_(False))
            .limit(limit)
            .all()
        )

        count = 0  # 成功下载计数
        for index, media in enumerate(media_items):
            # 通过媒体 → 推文 → 用户 链路获取用户名，用于构建存储路径
            tweet = session.query(Tweet).filter(Tweet.id == media.tweet_id).one()
            username = tweet.user.username

            # 调用下载器下载文件，返回本地路径或 None
            path = self.downloader.download(media.media_url, username, tweet.tweet_id, index)

            if path:
                # 下载成功：记录本地路径并标记为已下载
                media.local_path = str(path)
                media.downloaded = True
                count += 1
            else:
                # 下载失败：记录错误信息，标记保持 downloaded=False
                media.download_error = "download failed"

        # 批量提交所有变更到数据库
        session.commit()
        logger.info(f"媒体批量下载完成: {count}/{len(media_items)}")
        return count
