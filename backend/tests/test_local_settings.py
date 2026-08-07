from pathlib import Path

from config.settings import local


def test_local_preview_uses_sqlite_without_changing_normal_development_database() -> None:
    assert local.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    database_name = local.DATABASES["default"]["NAME"]
    assert isinstance(database_name, Path)
    assert database_name.name == "local.sqlite3"
    assert local.CELERY_TASK_ALWAYS_EAGER is True
