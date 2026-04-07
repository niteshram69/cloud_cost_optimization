"""Celery worker entry point for the Cloudteck backend."""

from backend.app.workers.celery_app import celery_app

if __name__ == "__main__":
    celery_app.start()
