"""
数据库管理模块

负责 SQLAlchemy 引擎和会话的初始化与管理。提供：
  1. Database 类：封装引擎创建、WAL 模式启用、会话工厂
  2. get_db()：FastAPI 风格的依赖注入函数，自动管理会话生命周期
  3. init_database()：命令行初始化入口

支持 SQLite（默认）及其他 SQLAlchemy 兼容数据库（MySQL/PostgreSQL）。
SQLite 模式下自动启用 WAL（Write-Ahead Logging）模式以提升并发写入性能。
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.storage.models import Base, User
from src.utils.env import load_project_env
from src.utils.logger import logger

# 加载 .env 文件中的环境变量（如 DATABASE_URL）
load_project_env()

# 数据库连接地址，默认为项目 data 目录下的 SQLite 文件
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/twitter_data.db")


class Database:
    """
    数据库管理类

    封装了数据库引擎的创建、会话工厂的设置以及连接池的配置。
    全局单例 db = Database() 供整个项目共享使用。

    Attributes:
        database_url: 数据库连接字符串
        engine: SQLAlchemy 引擎实例（init_db() 调用后创建）
        SessionLocal: 线程安全的会话工厂（init_db() 调用后创建）
    """

    def __init__(self, database_url: str = DATABASE_URL):
        """
        Args:
            database_url: 数据库连接字符串。
                          支持 sqlite:///、mysql+pymysql://、postgresql:// 等格式。
        """
        self.database_url = database_url
        self.engine = None  # 引擎实例，在 init_db() 中赋值
        self.SessionLocal = None  # 会话工厂，在 init_db() 中赋值

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    def init_db(self):
        """
        初始化数据库引擎和会话工厂，并创建所有表。

        Supports: SQLite (default) and PostgreSQL (via DATABASE_URL env var).
        """
        is_sqlite = self.database_url.startswith("sqlite")
        is_postgres = self.database_url.startswith("postgresql")

        if is_sqlite:
            db_path = self.database_url.replace("sqlite:///", "")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        engine_kwargs = {
            "echo": False,
            "pool_pre_ping": True,
        }
        if is_sqlite:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        elif is_postgres:
            engine_kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "10"))
            engine_kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "20"))
            engine_kwargs["pool_recycle"] = 3600

        self.engine = create_engine(self.database_url, **engine_kwargs)

        if is_sqlite:
            with self.engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA foreign_keys=ON"))
                conn.commit()

        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine,
        )

        Base.metadata.create_all(bind=self.engine)
        from src.admin.refresh_token import _RTBase
        _RTBase.metadata.create_all(bind=self.engine, checkfirst=True)
        logger.info(f"数据库初始化完成: {'PostgreSQL' if self.is_postgres else 'SQLite'}")

    def get_session(self) -> Session:
        """
        获取一个新的数据库会话实例。

        每次调用返回一个独立的会话，调用方在使用完毕后需手动关闭。

        Returns:
            Session: SQLAlchemy 会话对象

        Raises:
            RuntimeError: 若数据库尚未初始化（未调用 init_db()）
        """
        if self.SessionLocal is None:
            raise RuntimeError("数据库未初始化，请先调用 db.init_db()")
        return self.SessionLocal()

    def close(self):
        """
        关闭数据库引擎，释放所有连接池资源。

        通常在应用关闭时调用，之后需重新 init_db() 才能继续使用。
        """
        if self.engine:
            self.engine.dispose()  # dispose() 会关闭连接池中的所有连接
            logger.info("数据库连接已关闭")


# 全局单例数据库实例，整个应用共享
db = Database()


def get_db() -> Session:
    """
    获取数据库会话（依赖注入用）

    设计为 FastAPI Depends() 或生成器上下文管理器使用。自动在 finally 中
    关闭会话，确保资源释放。

    Yields:
        Session: 数据库会话实例

    Example:
        # FastAPI 依赖注入
        @app.get("/users")
        def list_users(db: Session = Depends(get_db)):
            return db.query(User).all()

        # 手动使用
        with next(get_db()) as session:
            users = session.query(User).all()
    """
    session = db.get_session()
    try:
        yield session  # 将会话传递给调用方
    finally:
        session.close()  # 无论成功或异常，都确保关闭会话


def init_database():
    """
    初始化数据库（命令行工具入口）

    启动时执行：创建表 → 检查是否为空库 → 提示配置监控用户。
    可通过 `python -m src.storage.database --init` 调用。
    """
    db.init_db()
    logger.info("数据库表创建完成")

    # 检查当前数据库中是否有监控用户
    session = db.get_session()
    try:
        user_count = session.query(User).count()
        if user_count == 0:
            logger.info("数据库为空，可通过 data/users.json 添加监控用户")
    finally:
        session.close()


# 命令行入口：支持 --init 参数初始化数据库
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        init_database()
    else:
        print("使用方法: python database.py --init")
