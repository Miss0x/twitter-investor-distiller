"""数据库管理模块"""
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.storage.models import Base, User
from src.utils.env import load_project_env
from src.utils.logger import logger

load_project_env()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/twitter_data.db")


class Database:
    """数据库管理类"""

    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None

    def init_db(self):
        """初始化数据库"""
        if self.database_url.startswith("sqlite"):
            db_path = self.database_url.replace("sqlite:///", "")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(
            self.database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False} if self.database_url.startswith("sqlite") else {},
        )

        if self.database_url.startswith("sqlite"):
            with self.engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.commit()

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

        Base.metadata.create_all(bind=self.engine)
        logger.info(f"数据库初始化完成: {self.database_url}")

    def get_session(self) -> Session:
        """获取数据库会话"""
        if self.SessionLocal is None:
            raise RuntimeError("数据库未初始化，请先调用 db.init_db()")
        return self.SessionLocal()

    def close(self):
        """关闭数据库连接"""
        if self.engine:
            self.engine.dispose()
            logger.info("数据库连接已关闭")


# 全局数据库实例
db = Database()


def get_db() -> Session:
    """获取数据库会话（依赖注入用）"""
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()


def init_database():
    """初始化数据库（命令行工具）"""
    db.init_db()
    logger.info("数据库表创建完成")

    session = db.get_session()
    try:
        user_count = session.query(User).count()
        if user_count == 0:
            logger.info("数据库为空，可以通过 config/users.yaml 添加监控用户")
    finally:
        session.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        init_database()
    else:
        print("使用方法: python database.py --init")

