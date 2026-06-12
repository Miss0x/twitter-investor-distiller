"""Cryptographic utilities for per-user config encryption.

Uses Fernet (AES-128-CBC + HMAC-SHA256) with per-user derived keys.
Master key from ENCRYPTION_KEY env var; per-user keys derived via HMAC.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from base64 import urlsafe_b64encode

from cryptography.fernet import Fernet

_master_key: bytes | None = None


def _ensure_master_key() -> bytes:
    global _master_key
    if _master_key is not None:
        return _master_key
    key = os.getenv("ENCRYPTION_KEY", "")
    if key:
        _master_key = key.encode()  # raw Fernet key from env
    else:
        # Auto-generate and persist for dev
        from pathlib import Path
        keyfile = Path("data/.master_key")
        if keyfile.exists():
            _master_key = keyfile.read_bytes()
        else:
            _master_key = Fernet.generate_key()
            keyfile.parent.mkdir(parents=True, exist_ok=True)
            keyfile.write_bytes(_master_key)
            os.environ["ENCRYPTION_KEY"] = _master_key.decode()
    return _master_key


def derive_user_key(tenant_id: str) -> bytes:
    """Derive per-user Fernet key from master key + tenant_id.

    Uses HMAC-SHA256(master_key, tenant_id) → first 32 bytes → base64 encode.
    """
    master = _ensure_master_key()
    raw = hmac.digest(master, tenant_id.encode("utf-8"), hashlib.sha256)
    return urlsafe_b64encode(raw)


def encrypt_config(data: dict, user_key: bytes) -> str:
    """Encrypt a JSON-serializable dict to a Fernet token string."""
    fernet = Fernet(user_key)
    plaintext = json_dumps(data).encode("utf-8")
    return fernet.encrypt(plaintext).decode("utf-8")


def decrypt_config(ciphertext: str, user_key: bytes) -> dict:
    """Decrypt a Fernet token back to a dict."""
    fernet = Fernet(user_key)
    plaintext = fernet.decrypt(ciphertext.encode("utf-8"))
    return json_loads(plaintext.decode("utf-8"))


def json_dumps(data: dict) -> str:
    import json
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def json_loads(s: str) -> dict:
    import json
    return json.loads(s)
