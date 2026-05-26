"""数据模型定义"""
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """Twitter 用户模型"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200))
    description = Column(Text)
    profile_image_url = Column(String(500))
    followers_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    tweet_count = Column(Integer, default=0)
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=999)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    last_crawled_at = Column(DateTime)

    tweets = relationship("Tweet", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(username='{self.username}', display_name='{self.display_name}')>"


class Tweet(Base):
    """推文模型"""

    __tablename__ = "tweets"

    id = Column(Integer, primary_key=True)
    tweet_id = Column(String(50), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    text = Column(Text, nullable=False)
    created_at_twitter = Column(DateTime, nullable=False)

    like_count = Column(Integer, default=0)
    retweet_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)
    quote_count = Column(Integer, default=0)
    view_count = Column(Integer, default=0)

    is_retweet = Column(Boolean, default=False)
    is_reply = Column(Boolean, default=False)
    is_quote = Column(Boolean, default=False)

    replied_to_tweet_id = Column(String(50))
    replied_to_user = Column(String(100))
    replied_text = Column(Text)
    quoted_tweet_id = Column(String(50))
    quoted_user = Column(String(100))
    quoted_text = Column(Text)

    has_media = Column(Boolean, default=False)
    media_count = Column(Integer, default=0)

    url = Column(String(500))
    extra_data = Column(JSON)

    is_vectorized = Column(Boolean, default=False)
    vectorized_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="tweets")
    media = relationship("Media", back_populates="tweet", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tweets_user_created", "user_id", "created_at_twitter"),
    )

    def __repr__(self):
        return f"<Tweet(tweet_id='{self.tweet_id}', text='{self.text[:50]}...')>"


class Media(Base):
    """媒体文件模型"""

    __tablename__ = "media"

    id = Column(Integer, primary_key=True)
    tweet_id = Column(Integer, ForeignKey("tweets.id"), nullable=False)

    media_type = Column(String(20), nullable=False)
    media_url = Column(String(500), nullable=False)
    local_path = Column(String(500))

    width = Column(Integer)
    height = Column(Integer)
    duration = Column(Integer)
    file_size = Column(Integer)

    downloaded = Column(Boolean, default=False)
    download_error = Column(Text)

    created_at = Column(DateTime, default=datetime.now)

    tweet = relationship("Tweet", back_populates="media")

    def __repr__(self):
        return f"<Media(type='{self.media_type}', url='{self.media_url}')>"


class CrawlLog(Base):
    """采集日志模型"""

    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    status = Column(String(20), nullable=False)
    tweets_collected = Column(Integer, default=0)
    media_downloaded = Column(Integer, default=0)

    error_message = Column(Text)
    duration_seconds = Column(Integer)

    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)

    def __repr__(self):
        return f"<CrawlLog(user_id={self.user_id}, status='{self.status}', tweets={self.tweets_collected})>"


class VectorMetadata(Base):
    """向量元数据模型"""

    __tablename__ = "vector_metadata"

    id = Column(Integer, primary_key=True)
    tweet_id = Column(Integer, ForeignKey("tweets.id"), nullable=False)

    vector_id = Column(String(100), unique=True, nullable=False)
    chunk_index = Column(Integer, default=0)
    chunk_text = Column(Text)

    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<VectorMetadata(vector_id='{self.vector_id}', tweet_id={self.tweet_id})>"


class PipelineTask(Base):
    """流水线任务队列。"""

    __tablename__ = "pipeline_tasks"

    id = Column(Integer, primary_key=True)
    task_type = Column(String(32), nullable=False, index=True)  # analyze / fetch_price / portrait
    status = Column(String(16), nullable=False, default="pending", index=True)  # pending / running / done / failed
    payload = Column(Text, nullable=False)  # JSON
    result = Column(Text)
    error_msg = Column(Text)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f"<PipelineTask(id={self.id}, type='{self.task_type}', status='{self.status}')>"
