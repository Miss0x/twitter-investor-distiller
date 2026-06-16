"""
数据模型定义模块

本模块使用 SQLAlchemy ORM 定义了推特用户蒸馏系统的全部数据表结构。
包括 6 个核心表：
  - User:     监控的 Twitter 用户信息
  - Tweet:    采集到的推文数据
  - Media:    推文中的媒体文件（图片/视频）
  - CrawlLog: 采集任务的执行日志
  - VectorMetadata: 推文向量化后的元数据（用于语义检索）
  - PipelineTask:   异步流水线任务队列

表之间通过 ForeignKey 建立关联，配合 relationship 实现 ORM 级联操作。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import declarative_base, relationship

# SQLAlchemy 声明式基类，所有 ORM 模型必须继承自它
Base = declarative_base()


class User(Base):
    """
    Twitter 监控用户模型

    存储需要监控的 Twitter 用户的基本信息和采集状态。
    每个用户可拥有多条推文（一对多关系），删除用户时级联删除其所有推文。
    """

    __tablename__ = "users"

    # ---- 基本信息 ----
    id = Column(Integer, primary_key=True)  # 自增主键
    username = Column(String(100), unique=True, nullable=False, index=True)  # Twitter 用户名（@后面的部分），唯一且不可为空
    display_name = Column(String(200))  # 用户的展示名称（昵称）
    description = Column(Text)  # 用户的个人简介/签名

    # ---- 头像 ----
    profile_image_url = Column(String(500))  # 头像图片的远程 URL

    # ---- 统计数据 ----
    followers_count = Column(Integer, default=0)  # 粉丝数
    following_count = Column(Integer, default=0)  # 关注数
    tweet_count = Column(Integer, default=0)  # 发推总数

    # ---- 采集控制 ----
    enabled = Column(Boolean, default=True)  # 是否启用对该用户的监控与采集
    priority = Column(Integer, default=999)  # 采集优先级，数值越小越优先

    # ---- 时间戳 ----
    created_at = Column(DateTime, default=datetime.now)  # 用户记录创建时间
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)  # 记录更新时间，每次修改自动刷新
    last_crawled_at = Column(DateTime)  # 最近一次完成采集的时间

    # ---- 关联关系 ----
    # 一对多：一个用户拥有多条推文，删除用户时级联删除所有关联推文
    tweets = relationship("Tweet", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(username='{self.username}', display_name='{self.display_name}')>"


class Tweet(Base):
    """
    推文数据模型

    存储从 Twitter 采集到的单条推文的所有信息，包括：
    - 推文正文与发布元数据
    - 互动数据（点赞、转发、回复、引用、浏览）
    - 引用/回复上下文
    - 媒体文件关联
    - 向量化状态

    每条推文归属于一个 User，可包含多条 Media。
    """

    __tablename__ = "tweets"

    # ---- 主键与标识 ----
    id = Column(Integer, primary_key=True)  # 数据库自增主键
    tweet_id = Column(String(50), unique=True, nullable=False, index=True)  # Twitter 平台上的推文 ID（字符串，避免大数溢出）
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # 外键：所属用户

    # ---- 推文内容 ----
    text = Column(Text, nullable=False)  # 推文正文（完整文本）
    created_at_twitter = Column(DateTime, nullable=False)  # 推文在 Twitter 上的发布时间

    # ---- 互动数据 ----
    like_count = Column(Integer, default=0)  # 点赞数
    retweet_count = Column(Integer, default=0)  # 转发数
    reply_count = Column(Integer, default=0)  # 回复数
    quote_count = Column(Integer, default=0)  # 引用数
    view_count = Column(Integer, default=0)  # 浏览次数

    # ---- 推文类型标记 ----
    is_retweet = Column(Boolean, default=False)  # 是否为纯转发
    is_reply = Column(Boolean, default=False)  # 是否为回复
    is_quote = Column(Boolean, default=False)  # 是否为引用推文（带评论转发）

    # ---- 回复上下文（当 is_reply=True 时有值） ----
    replied_to_tweet_id = Column(String(50))  # 被回复的推文 ID
    replied_to_user = Column(String(100))  # 被回复的用户名
    replied_text = Column(Text)  # 被回复推文的正文（用于后续分析上下文）

    # ---- 引用上下文（当 is_quote=True 时有值） ----
    quoted_tweet_id = Column(String(50))  # 被引用的推文 ID
    quoted_user = Column(String(100))  # 被引用的用户名
    quoted_text = Column(Text)  # 被引用推文的正文

    # ---- 媒体文件标记 ----
    has_media = Column(Boolean, default=False)  # 是否包含媒体文件（图片/视频）
    media_count = Column(Integer, default=0)  # 媒体文件数量

    # ---- 其他 ----
    url = Column(String(500))  # 推文的完整 URL
    extra_data = Column(JSON)  # 扩展数据（JSON 格式，存储爬虫返回的额外字段）

    # ---- 向量化状态 ----
    is_vectorized = Column(Boolean, default=False)  # 是否已完成向量化处理
    vectorized_at = Column(DateTime)  # 向量化完成时间

    # ---- 时间戳 ----
    created_at = Column(DateTime, default=datetime.now)  # 记录入库时间
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)  # 记录更新时间

    # ---- 关联关系 ----
    # 多对一：每条推文属于一个用户
    user = relationship("User", back_populates="tweets")
    # 一对多：一条推文可包含多条媒体记录，删除推文时级联删除媒体
    media = relationship("Media", back_populates="tweet", cascade="all, delete-orphan")

    # ---- 联合索引 ----
    # 加速按用户+发布时间查询推文的场景（最常见的查询模式）
    __table_args__ = (
        Index("ix_tweets_user_created", "user_id", "created_at_twitter"),
    )

    def __repr__(self):
        return f"<Tweet(tweet_id='{self.tweet_id}', text='{self.text[:50]}...')>"


class Media(Base):
    """
    媒体文件模型

    存储推文中包含的媒体文件（图片/GIF/视频）的元信息及下载状态。
    每条媒体记录归属于一条 Tweet，可记录下载到本地的路径。
    """

    __tablename__ = "media"

    # ---- 主键与关联 ----
    id = Column(Integer, primary_key=True)  # 自增主键
    tweet_id = Column(Integer, ForeignKey("tweets.id"), nullable=False)  # 外键：所属推文

    # ---- 媒体基本信息 ----
    media_type = Column(String(20), nullable=False)  # 媒体类型：photo / video / animated_gif
    media_url = Column(String(500), nullable=False)  # 媒体的远程 URL（最佳质量版本）
    local_path = Column(String(500))  # 下载到本地的文件路径（未下载时为空）

    # ---- 媒体元数据 ----
    width = Column(Integer)  # 图片/视频宽度（像素）
    height = Column(Integer)  # 图片/视频高度（像素）
    duration = Column(Integer)  # 视频时长（毫秒，仅视频有效）
    file_size = Column(Integer)  # 文件大小（字节）

    # ---- 下载状态 ----
    downloaded = Column(Boolean, default=False)  # 是否已成功下载
    download_error = Column(Text)  # 下载失败时的错误信息

    # ---- 时间戳 ----
    created_at = Column(DateTime, default=datetime.now)  # 记录创建时间

    # ---- 关联关系 ----
    # 多对一：每条媒体记录属于一条推文
    tweet = relationship("Tweet", back_populates="media")

    def __repr__(self):
        return f"<Media(type='{self.media_type}', url='{self.media_url}')>"


class CrawlLog(Base):
    """
    采集日志模型

    记录每轮推文采集任务的执行情况，包括：
    - 采集了哪个用户
    - 成功/失败状态
    - 采集到多少推文、下载了多少媒体
    - 耗时与错误信息

    用于监控采集管道的健康状况和排查故障。
    """

    __tablename__ = "crawl_logs"

    # ---- 主键与关联 ----
    id = Column(Integer, primary_key=True)  # 自增主键
    user_id = Column(Integer, ForeignKey("users.id"))  # 外键：被采集的用户（可为空，表示系统级任务）

    # ---- 执行结果 ----
    status = Column(String(20), nullable=False)  # 任务状态：success / failed
    tweets_collected = Column(Integer, default=0)  # 本轮新采集到的推文数
    media_downloaded = Column(Integer, default=0)  # 本轮下载的媒体文件数

    # ---- 错误与耗时 ----
    error_message = Column(Text)  # 失败时的错误详情
    duration_seconds = Column(Integer)  # 任务耗时（秒）

    # ---- 时间戳 ----
    started_at = Column(DateTime, nullable=False)  # 任务开始时间
    finished_at = Column(DateTime)  # 任务结束时间

    def __repr__(self):
        return f"<CrawlLog(user_id={self.user_id}, status='{self.status}', tweets={self.tweets_collected})>"


class VectorMetadata(Base):
    """
    向量元数据模型

    存储推文文本向量化后的元信息。一条推文可能被切分为多个文本块（chunk），
    每个块对应一个独立的向量记录。用于支持向量相似度检索（语义搜索）。
    """

    __tablename__ = "vector_metadata"

    # ---- 主键与关联 ----
    id = Column(Integer, primary_key=True)  # 自增主键
    tweet_id = Column(Integer, ForeignKey("tweets.id"), nullable=False)  # 外键：所属推文

    # ---- 向量信息 ----
    vector_id = Column(String(100), unique=True, nullable=False)  # 向量在向量数据库中的唯一标识
    chunk_index = Column(Integer, default=0)  # 文本块序号（从 0 开始，用于拼接还原）
    chunk_text = Column(Text)  # 该文本块的原文内容

    # ---- 时间戳 ----
    created_at = Column(DateTime, default=datetime.now)  # 记录创建时间

    def __repr__(self):
        return f"<VectorMetadata(vector_id='{self.vector_id}', tweet_id={self.tweet_id})>"


class PipelineTask(Base):
    """
    流水线任务队列模型

    实现简易的任务队列，存储需要异步执行的分析任务。支持以下任务类型：
      - analyze:     分析推文内容（如情感、主题提取）
      - fetch_price: 获取关联资产价格
      - portrait:    生成用户画像

    任务状态流转：
      pending → running → done
                       → failed (可重试)
    """

    __tablename__ = "pipeline_tasks"

    # ---- 主键 ----
    id = Column(Integer, primary_key=True)  # 自增主键

    # ---- 任务定义 ----
    task_type = Column(String(32), nullable=False, index=True)  # 任务类型：analyze / fetch_price / portrait
    status = Column(
        String(16), nullable=False, default="pending", index=True
    )  # 任务状态：pending（等待执行）/ running（执行中）/ done（已完成）/ failed（失败）

    # ---- 任务数据 ----
    payload = Column(Text, nullable=False)  # 任务输入数据（JSON 格式字符串）
    result = Column(Text)  # 任务执行结果（JSON 格式字符串，完成后填充）
    error_msg = Column(Text)  # 失败时的错误信息

    # ---- 时间戳 ----
    created_at = Column(DateTime, default=datetime.now)  # 任务创建时间
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)  # 状态更新时间

    def __repr__(self):
        return f"<PipelineTask(id={self.id}, type='{self.task_type}', status='{self.status}')>"
