"""Secrets encryption — Cloudflare tokens and proxy credentials are stored encrypted at rest.

Never log plaintext secrets. This module is the only place handling raw secrets.
"""
from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    # Accept any passphrase: derive a stable 32-byte key from it.
    if not key.startswith("gAAAAA") and len(key) != 44:
        digest = hashlib.sha256(key.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:  # wrong key or corrupted data
        raise RuntimeError("Failed to decrypt secret — check ENCRYPTION_KEY") from exc


def generate_subscription_token() -> str:
    """Secure, unguessable subscription token (no DB ids exposed)."""
    return secrets.token_urlsafe(24)


def generate_uuid() -> str:
    import uuid
    return str(uuid.uuid4())


def generate_trojan_password() -> str:
    return secrets.token_urlsafe(24)


def generate_x25519_keypair() -> tuple[str, str]:
    """Generate REALITY x25519 key pair in Xray wire format (base64url, no padding)."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    key = X25519PrivateKey.generate()
    priv = key.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
    return b64(priv), b64(pub)


def generate_short_ids(n: int = 2) -> list[str]:
    return [secrets.token_hex(4) for _ in range(n)]
