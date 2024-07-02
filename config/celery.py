import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.django.local')

celery = Celery('config', backend="redis://localhost",)
celery.config_from_object('django.conf:django', namespace='CELERY')

celery.autodiscover_tasks()
