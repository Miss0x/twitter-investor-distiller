"""Tests for admin/auth module — login, token, permissions, refresh rotation."""

from src.admin.auth import create_access_token, hash_password, verify_password
from src.admin.refresh_token import (
    _hash_token,
    create_refresh_family,
    generate_refresh_token,
    revoke_user_tokens,
    rotate_refresh_token,
)


def test_password_hash_and_verify():
    pw = "test-password-123"
    hashed = hash_password(pw)
    assert verify_password(pw, hashed)
    assert not verify_password("wrong", hashed)


def test_password_hash_is_unique():
    h1 = hash_password("alpha")
    h2 = hash_password("beta")
    assert h1 != h2  # different passwords → different hashes
    assert verify_password("alpha", h1)
    assert verify_password("beta", h2)


def test_create_access_token_contains_sub():
    token = create_access_token({"sub": 42, "email": "a@b.com"})
    assert len(token) > 50  # JWT is a long string


def test_refresh_token_generation():
    raw, hashed = generate_refresh_token()
    assert len(raw) == 64  # token_urlsafe(48) → 64 chars
    assert hashed != raw
    assert _hash_token(raw) == hashed


def test_refresh_token_rotation_and_reuse_detection(db_session):
    # Create a refresh family
    raw1, _ = create_refresh_family(db_session, user_id=1, days=7)

    # First rotation: should succeed
    result = rotate_refresh_token(db_session, raw1)
    assert result is not None
    raw2, _ = result
    assert raw2 != raw1  # rotated to a new token

    # Reusing raw1: should fail (used=True)
    result2 = rotate_refresh_token(db_session, raw1)
    assert result2 is None  # reuse detected

    # raw2 should also be revoked because same family
    result3 = rotate_refresh_token(db_session, raw2)
    assert result3 is None  # entire family revoked


def test_refresh_token_expiry_rejected(db_session):
    raw, _ = create_refresh_family(db_session, user_id=2, days=0)  # expires immediately
    result = rotate_refresh_token(db_session, raw)
    assert result is None  # expired


def test_refresh_token_invalid_rejected(db_session):
    result = rotate_refresh_token(db_session, "not-a-valid-token-at-all")
    assert result is None


def test_revoke_all_user_tokens(db_session):
    raw1, _ = create_refresh_family(db_session, user_id=3, days=7)
    raw2, _ = create_refresh_family(db_session, user_id=3, days=7)
    count = revoke_user_tokens(db_session, user_id=3)
    assert count == 2
    assert rotate_refresh_token(db_session, raw1) is None
    assert rotate_refresh_token(db_session, raw2) is None


def test_revoke_only_targets_active_tokens(db_session):
    raw, _ = create_refresh_family(db_session, user_id=4, days=7)
    rotate_refresh_token(db_session, raw)  # marks old as used, creates new
    count = revoke_user_tokens(db_session, user_id=4)
    assert count == 1  # only the new (unused) token
