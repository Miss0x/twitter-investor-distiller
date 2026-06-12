"""Pytest fixtures for auth/admin tests."""
import pytest
from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone


class _TestBase(DeclarativeBase):
    pass


class _TestRT(_TestBase):
    __tablename__ = "auth_refresh_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    family = Column(String(36), nullable=False, index=True)
    used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


@pytest.fixture
def db_session():
    """In-memory SQLite session for refresh token tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    _TestBase.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    # Patch the RefreshToken class in the module
    import src.admin.refresh_token as rt
    rt.RefreshToken = _TestRT
    yield session
    session.close()
    _TestBase.metadata.drop_all(bind=engine)
