import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_hasher = PasswordHasher()

TOKEN_PREFIX = "pts_"
SESSION_COOKIE = "plantasaurus_session"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def generate_api_token() -> tuple[str, str, str]:
    """Return (full_token, display_prefix, sha256_hash)."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, token[: len(TOKEN_PREFIX) + 6], hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SessionSigner:
    def __init__(self, secret_key: str, max_age_seconds: int):
        self._s = URLSafeTimedSerializer(secret_key, salt="plantasaurus-session")
        self.max_age = max_age_seconds

    def dumps(self, user_id: int, password_hash: str | None) -> str:
        # Include a fingerprint of the password hash so changing password invalidates sessions.
        return self._s.dumps({"uid": user_id, "pw": _fingerprint(password_hash)})

    def loads(self, value: str) -> tuple[int, str] | None:
        try:
            data = self._s.loads(value, max_age=self.max_age)
        except (BadSignature, SignatureExpired):
            return None
        if not isinstance(data, dict) or "uid" not in data:
            return None
        return int(data["uid"]), str(data.get("pw", ""))


def _fingerprint(password_hash: str | None) -> str:
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:16]


def session_matches(password_hash: str | None, fingerprint: str) -> bool:
    return secrets.compare_digest(_fingerprint(password_hash), fingerprint)
