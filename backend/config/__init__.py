"""Django 项目配置包。"""

from config.celery import app as celery_app

__all__ = ("celery_app",)
