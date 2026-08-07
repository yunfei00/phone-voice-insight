"""生产环境设置。"""

from config.settings.base import *  # noqa: F403

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)  # noqa: F405
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", True)  # noqa: F405
CSRF_TRUSTED_ORIGINS = [
    item.strip()
    for item in env("CSRF_TRUSTED_ORIGINS", "").split(",")  # noqa: F405
    if item.strip()
]
