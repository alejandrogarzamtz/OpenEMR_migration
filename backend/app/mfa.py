import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet

from .config import settings


def cipher() -> Fernet:
    configured = settings.mfa_encryption_key.get_secret_value() if settings.mfa_encryption_key else ""
    if configured:
        return Fernet(configured.encode("ascii"))
    fallback = hashlib.sha256(settings.jwt_secret.get_secret_value().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(fallback))


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_secret(secret: str) -> bytes:
    return cipher().encrypt(secret.encode("ascii"))


def decrypt_secret(value: bytes) -> str:
    return cipher().decrypt(value).decode("ascii")

def totp_at(secret: str, step: int) -> str:
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def matching_step(secret: str, code: str, now: int | None = None) -> int | None:
    if len(code) != 6 or not code.isdigit():
        return None
    current = (now if now is not None else int(time.time())) // 30
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp_at(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, email: str) -> str:
    label = quote(f"OpenRM:{email}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer=OpenRM&algorithm=SHA1&digits=6&period=30"


def recovery_codes(count: int = 10) -> list[str]:
    return [f"{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}" for _ in range(count)]


def recovery_digest(code: str) -> str:
    normalized = code.strip().upper().replace(" ", "")
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()
