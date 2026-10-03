"""Security utilities: JWT, password hashing, API key encryption."""
import jwt
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from app.config import Config


def generate_token(user_id, username, role="user"):
    """Generate JWT token for authentication.

    role: "user" for normal authenticated users, "guest" for read-only guests.
    """
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=Config.JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")
    return token


def verify_token(token):
    """Verify JWT token and return payload. Returns None if invalid."""
    try:
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
        return payload
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _get_fernet():
    """Get Fernet instance for API key encryption.

    Derives a 32-byte key from ENCRYPTION_KEY via SHA-256, then base64-encodes
    it for Fernet. This ensures full entropy regardless of the input key length.
    """
    key = hashlib.sha256(Config.ENCRYPTION_KEY.encode()).digest()
    key_bytes = base64.urlsafe_b64encode(key)
    return Fernet(key_bytes)


def encrypt_api_key(api_key):
    """Encrypt API key for storage."""
    f = _get_fernet()
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key):
    """Decrypt API key for use."""
    try:
        f = _get_fernet()
        return f.decrypt(encrypted_key.encode()).decode()
    except Exception:
        return ""
