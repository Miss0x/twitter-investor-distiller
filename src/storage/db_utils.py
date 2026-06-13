"""Database session context manager — reduces boilerplate try/finally."""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def db_session():
    """提供 session 并自动关闭, 减少 try/finally 样板代码。

    Usage:
        with db_session() as session:
            user = session.query(AuthUser).filter(...).first()
    """
    from src.storage.database import db
    session = db.get_session()
    try:
        yield session
    finally:
        session.close()
