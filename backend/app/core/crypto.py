"""Symmetric encryption for sensitive fields (LLM API keys, k8s tokens).

Uses Fernet (AES-128-CBC + HMAC-SHA256). Key sourced from env var
AIRW_ENCRYPTION_KEY (base64-urlsafe 32-byte key, generated via
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).

If AIRW_ENCRYPTION_KEY is not set, falls back to a key derived from
AIRW_SECRET_KEY (or a hardcoded dev key) with a console warning.
Production deployments MUST set AIRW_ENCRYPTION_KEY.
"""
import logging
import os
import base64
import hashlib

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_DEV_FALLBACK_KEY = b"airw-dev-only-DO-NOT-use-in-prod-aaaaaa"  # 32 bytes


def _get_or_warn() -> bytes:
    raw = os.environ.get("AIRW_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            return base64.urlsafe_b64decode(raw.encode())
        except Exception:
            pass
    # Fallback: derive from AIRW_SECRET_KEY or dev key
    seed = os.environ.get("AIRW_SECRET_KEY", "").strip() or "airw-dev"
    derived = hashlib.sha256(seed.encode()).digest()
    logger.warning(
        "AIRW_ENCRYPTION_KEY not set — using SHA-256(AIRW_SECRET_KEY || 'airw-dev'). "
        "Set AIRW_ENCRYPTION_KEY to a Fernet key in production!"
    )
    return base64.urlsafe_b64encode(derived + _DEV_FALLBACK_KEY[:0])[:44] + b"==="


_FERNET: Fernet | None = None


def _fernet() -> Fernet:
    global _FERNET
    if _FERNET is None:
        _FERNET = Fernet(_get_or_warn())
    return _FERNET


def encrypt(plaintext: str) -> str:
    """Encrypt a string, return URL-safe base64 token (str)."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a token back to plaintext. Empty token returns empty."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception as e:
        logger.error("decrypt failed: %s", e)
        return ""
