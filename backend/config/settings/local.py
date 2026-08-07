"""无需外部数据库的本地预览配置。

仅用于 UI 联调和快速体验；正式开发与部署仍使用 PostgreSQL。
"""

from config.settings.development import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "local.sqlite3",  # noqa: F405
    }
}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
