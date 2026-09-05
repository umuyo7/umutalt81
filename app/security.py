import base64
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
ARGON2 = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    return ARGON2.hash(password)


def _hash_password_scrypt(password: str) -> str:
    """Yalnız legacy test/veri geçişi için; yeni hash üretiminde kullanılmaz."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_encode(salt)}${_encode(derived)}"


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("$argon2"):
        try:
            return ARGON2.verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False
    try:
        scheme, n, r, p, salt, expected = password_hash.split("$", 5)
        if scheme != "scrypt":
            return False
        expected_bytes = _decode(expected)
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected_bytes),
        )
        return hmac.compare_digest(derived, expected_bytes)
    except (TypeError, ValueError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    if not password_hash.startswith("$argon2"):
        return True
    try:
        return ARGON2.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True
