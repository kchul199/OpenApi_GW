"""Celery 애플리케이션 설정."""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "coin_trader",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.trading_tasks",
        "app.tasks.ai_tasks",
        "app.tasks.maintenance_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # 큐 라우팅
    task_routes={
        "app.tasks.trading_tasks.*": {"queue": "trading"},
        "app.tasks.ai_tasks.*": {"queue": "ai_advice"},
        "app.tasks.maintenance_tasks.*": {"queue": "maintenance"},
    },
    # Beat 스케줄 (Redbeat 사용 시 override 됨)
    beat_schedule={
        "run-active-strategies-every-minute": {
            "task": "app.tasks.trading_tasks.run_all_active_strategies",
            "schedule": 60.0,
        },
        "sync-balances-every-5-minutes": {
            "task": "app.tasks.maintenance_tasks.sync_all_balances",
            "schedule": 300.0,
        },
        "cleanup-expired-tokens-daily": {
            "task": "app.tasks.maintenance_tasks.cleanup_expired_tokens",
            "schedule": 86400.0,
        },
    },
)
