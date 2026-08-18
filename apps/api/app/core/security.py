import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger(__name__)


def _parse_key(raw: str) -> bytes:
    """Parse a hex-encoded 32-byte encryption key."""
    if not raw:
        raise RuntimeError("encryption_key is not set; generate a 32-byte hex string")
    try:
        key = bytes.fromhex(raw.strip())
    except ValueError as exc:
        raise RuntimeError("encryption_key must be a valid hex string") from exc
    if len(key) != 32:
        raise RuntimeError("encryption_key must be 32 bytes (64 hex characters)")
    return key


def _get_encryption_key() -> bytes:
    return _parse_key(settings.encryption_key)


def _get_previous_keys() -> list[bytes]:
    """Parse the comma-separated previous keys (may be empty)."""
    raw = settings.encryption_key_previous.strip()
    if not raw:
        return []
    keys: list[bytes] = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                keys.append(_parse_key(part))
            except RuntimeError:
                logger.warning("Skipping malformed previous encryption key")
    if not keys:
        logger.error(
            "encryption_key_previous is non-empty but contained zero valid keys"
        )
    return keys


def encrypt_token(plaintext: str) -> str:
    """Encrypt a bot token with the *current* key (AES-256-GCM). Returns a
    base64-encoded ciphertext (nonce || data)."""
    key = _get_encryption_key()
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_token(encoded: str) -> str:
    """Decrypt a bot token. Tries the current key first, then falls back to
    any configured previous keys so that key rotation doesn't invalidate
    existing encrypted tokens."""
    keys = [_get_encryption_key()] + _get_previous_keys()
    raw = base64.urlsafe_b64decode(encoded)
    nonce, ciphertext = raw[:12], raw[12:]

    last_exc: Exception | None = None
    for i, key in enumerate(keys):
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, None).decode()
            if i > 0:
                logger.info(
                    "Token decrypted with previous key #%d — token is still "
                    "encrypted with an old key. It will be re-encrypted with "
                    "the current key on next explicit token write (e.g., OAuth "
                    "refresh or credential update).",
                    i,
                )
            return plaintext
        except Exception as exc:
            last_exc = exc

    raise RuntimeError(
        "Failed to decrypt token with any available key "
        f"({len(keys)} key(s) tried)"
    ) from last_exc
