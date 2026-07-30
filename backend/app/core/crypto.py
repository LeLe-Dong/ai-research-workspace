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
import binascii

logger = logging.getLogger(__name__)


def _get_or_warn() -> bytes:
    """Resolve the Fernet key from env, falling back to a derived one.

    Returns a Fernet-compatible key — a 32 raw-byte buffer **as a base64
    URL-safe encoded string**. This is what Fernet() expects; passing raw
    32 bytes raises "Fernet key must be 32 url-safe base64-encoded bytes".
    """
    raw = os.environ.get("AIRW_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            Fernet(raw.encode())  # raises if env value is not a valid Fernet key
            return raw.encode()
        except (ValueError, TypeError, binascii.Error) as e:
            logger.warning(
                f"AIRW_ENCRYPTION_KEY is set but is NOT a valid Fernet key "
                f"({type(e).__name__}: {e}). Falling back to a derived dev key. "
                "Generate a real one: "
                'python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            )
    # Fallback: derive a 32-byte raw key and base64-urlsafe-encode it (44 chars).
    seed = os.environ.get("AIRW_SECRET_KEY", "").strip() or "airw-dev"
    sha = hashlib.sha256(seed.encode()).digest()  # 32 bytes
    return base64.urlsafe_b64encode(sha)


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
