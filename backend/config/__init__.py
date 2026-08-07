"""Django 项目配置包。"""

import sys
from pathlib import Path

backend_directory = Path(__file__).resolve().parent.parent
repository_root = backend_directory if (backend_directory / "collectors").is_dir() else backend_directory.parent
if str(repository_root) not in sys.path:
    sys.path.insert(0, str(repository_root))

from config.celery import app as celery_app  # noqa: E402

__all__ = ("celery_app",)
