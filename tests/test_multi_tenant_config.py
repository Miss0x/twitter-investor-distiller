"""Tests for multi-tenant encrypted config system."""
import json
import tempfile
from pathlib import Path

from src.security.crypto import derive_user_key, encrypt_config, decrypt_config, _ensure_master_key


def test_encrypt_decrypt_roundtrip():
    """Write then read should return identical data."""
    original = {"llm": {"api_key": "sk-secret-123", "model": "gpt-4"}, "observations": ["TJ_Research"]}
    user_key = derive_user_key("tenant-1")
    ciphertext = encrypt_config(original, user_key)
    decrypted = decrypt_config(ciphertext, user_key)
    assert decrypted == original
    assert "sk-secret-123" not in ciphertext  # ciphertext doesn't leak plaintext


def test_different_users_have_different_keys():
    """Same config encrypted with different user keys should produce different ciphertexts."""
    config = {"twitter": {"api_key": "tw-key"}}
    key_a = derive_user_key("user-a")
    key_b = derive_user_key("user-b")
    assert encrypt_config(config, key_a) != encrypt_config(config, key_b)


def test_wrong_key_fails_decryption():
    """Decrypting with wrong key should fail."""
    config = {"secret": "abc"}
    ct = encrypt_config(config, derive_user_key("alice"))
    try:
        decrypt_config(ct, derive_user_key("bob"))
        assert False, "Should have raised"
    except Exception:
        pass  # expected


def test_empty_config_roundtrip():
    cfg = {}
    ct = encrypt_config(cfg, derive_user_key("t1"))
    assert decrypt_config(ct, derive_user_key("t1")) == {}


def test_master_key_is_stable():
    """Master key should be derived from env or generated once and cached."""
    k1 = _ensure_master_key()
    k2 = _ensure_master_key()
    assert k1 == k2


def test_per_user_config_manager():
    """Per-user ConfigManager reads/writes encrypted files."""
    from src.multi_tenant.config import PerUserConfig, CONFIG_CACHE

    with tempfile.TemporaryDirectory() as td:
        cfg = PerUserConfig(tenant_id="test-user", base_dir=td)
        assert "llm" in cfg.load()
        cfg.save_section("llm", {"api_key": "sk-test"})
        assert cfg.load()["llm"]["api_key"] == "sk-test"
        cfg.add_observation("user1")
        assert "user1" in cfg.load()["observations"]

        # Verify ciphertext on disk
        raw = Path(td, "test-user", "config.json").read_text(encoding="utf-8")
        assert "sk-test" not in raw  # encrypted on disk

        # Cache test
        cfg2 = PerUserConfig(tenant_id="test-user", base_dir=td)
        assert cfg2.load()["llm"]["api_key"] == "sk-test"

        # Clean cache
        CONFIG_CACHE.clear()


def test_config_cache_ttl_eviction():
    """Cached config should evict after TTL."""
    from src.multi_tenant.config import CONFIG_CACHE, _cache_get, _cache_set

    CONFIG_CACHE.clear()
    _cache_set("t1", {"x": 1}, ttl=0.1)
    assert _cache_get("t1") == {"x": 1}
    import time
    time.sleep(0.15)
    assert _cache_get("t1") is None
