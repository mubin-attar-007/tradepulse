"""At-rest encryption for broker credentials (libsodium secretbox).

MVP uses a single env-provided key (fixes the legacy plaintext-secret sin for
the actual paper/BYO-key threat model). Per-row DEKs + KMS envelope encryption
are deferred to the gated live-trading phase. Dormant until Phase 8.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from nacl.secret import SecretBox

from app.core.config import get_settings
from app.core.errors import AppError


class CredentialCipher:
    def __init__(self, key_b64: str) -> None:
        raw = base64.b64decode(key_b64)
        if len(raw) != SecretBox.KEY_SIZE:
            raise ValueError(f"BROKER_CRED_KEY must decode to {SecretBox.KEY_SIZE} bytes.")
        self._box = SecretBox(raw)

    def encrypt(self, plaintext: str) -> bytes:
        return bytes(self._box.encrypt(plaintext.encode()))

    def decrypt(self, token: bytes) -> str:
        return self._box.decrypt(bytes(token)).decode()


@lru_cache
def get_cipher() -> CredentialCipher:
    key = get_settings().broker_cred_key
    if not key:
        raise AppError("BROKER_CRED_KEY is not configured.")
    return CredentialCipher(key)
