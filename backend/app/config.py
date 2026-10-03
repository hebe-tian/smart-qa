"""Application configuration."""
import os
import secrets
import logging

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.environ.get("DB_DIR", os.path.join(BASE_DIR, "instance"))

_logger = logging.getLogger(__name__)


def _get_or_create_secret(env_key, length=48):
    """Get a secret from the environment, or create/load a persistent random secret.

    Avoids hardcoding default secrets. In development, generates a random secret
    and persists it to a file so tokens/encrypted data survive restarts.
    In production, set the environment variable explicitly.
    """
    env_val = os.environ.get(env_key)
    if env_val:
        return env_val

    secret_file = os.path.join(INSTANCE_DIR, f".{env_key.lower()}")
    try:
        with open(secret_file, "r") as f:
            val = f.read().strip()
            if val:
                return val
    except (FileNotFoundError, IOError):
        pass

    os.makedirs(INSTANCE_DIR, exist_ok=True)
    val = secrets.token_urlsafe(length)
    with open(secret_file, "w") as f:
        f.write(val)
    try:
        os.chmod(secret_file, 0o600)
    except OSError:
        pass
    _logger.warning(
        "%s not set in environment. Generated a random secret saved to %s. "
        "For production deployments, set the %s environment variable explicitly.",
        env_key, secret_file, env_key,
    )
    return val


class Config:
    SECRET_KEY = _get_or_create_secret("SECRET_KEY")

    # SQLite database - works on PythonAnywhere free tier
    DB_DIR = os.environ.get("DB_DIR", os.path.join(BASE_DIR, "instance"))
    DB_PATH = os.path.join(DB_DIR, "testcase.db")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 30},
    }

    # JWT settings
    JWT_EXPIRATION_HOURS = 24

    # API key encryption key for storing AI API keys
    ENCRYPTION_KEY = _get_or_create_secret("ENCRYPTION_KEY")

    # Registration: set REGISTRATION_ENABLED=false to disable open registration
    REGISTRATION_ENABLED = os.environ.get("REGISTRATION_ENABLED", "true").lower() == "true"

    # Upload limits (zip code package uploads)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max request body

    # Logging
    LOG_DIR = os.environ.get("LOG_DIR", os.path.join(BASE_DIR, "logs"))
    LOG_MAX_BYTES = 1024 * 512  # 512KB per log file
    LOG_BACKUP_COUNT = 3
    # Minimum level written to log files: DEBUG / INFO / WARNING / ERROR.
    # Defaults to INFO so debug traces stay out of the log files; set
    # LOG_LEVEL=DEBUG to restore full detail when troubleshooting.
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Frontend static files
    STATIC_FOLDER = os.path.join(BASE_DIR, "..", "frontend")
    STATIC_URL_PATH = ""
    TEMPLATE_FOLDER = os.path.join(BASE_DIR, "templates")

    # Default admin (created only when the database has no users).
    # Customize via the ADMIN_USERNAME / ADMIN_PASSWORD environment variables.
    DEFAULT_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def ensure_dirs():
    """Create required directories."""
    config = Config()
    for d in [config.DB_DIR, config.LOG_DIR]:
        os.makedirs(d, exist_ok=True)
