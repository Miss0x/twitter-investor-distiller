"""Celery app — async task execution for tweet collection and LLM analysis.

Tasks:
- collect_tweets: fetch tweets for a given user
- run_analysis: run AI analysis on collected tweets
- run_pipeline: full pipeline (collect → analyze → review)
- cleanup_tokens: clean expired refresh tokens
- check_price_alerts: check and trigger price alerts
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "twitter_distiller",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/2",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=600,
    task_time_limit=900,
)

# ── 定时任务调度 ──
celery_app.conf.beat_schedule = {
    "cleanup-expired-tokens": {
        "task": "src.pipeline.celery_app.cleanup_expired_tokens",
        "schedule": crontab(hour=3, minute=0),  # 每天凌晨 3 点
    },
    "check-price-alerts": {
        "task": "src.pipeline.celery_app.check_price_alerts",
        "schedule": crontab(minute="*/5"),  # 每 5 分钟
    },
}


@celery_app.task(name="src.pipeline.celery_app.collect_tweets")
def collect_tweets(username: str, count: int = 50):
    """采集指定用户的推文。"""
    from src.pipeline.task_executor import PipelineExecutor
    executor = PipelineExecutor()
    return executor.collect(username, count=count)


@celery_app.task(name="src.pipeline.celery_app.run_pipeline")
def run_pipeline(username: str):
    """完整流水线：采集 → 分析 → 治理评审。"""
    from src.pipeline.task_executor import PipelineExecutor
    executor = PipelineExecutor()
    collected = executor.collect(username)
    if not collected:
        return {"status": "no_data", "username": username}
    analyzed = executor.analyze(username)
    return {"status": "ok", "username": username, "tweets": len(collected), "signals": analyzed}


@celery_app.task(name="src.pipeline.celery_app.cleanup_expired_tokens")
def cleanup_expired_tokens():
    """清理过期 Refresh Token。"""
    from src.admin.refresh_token import cleanup_expired_tokens
    from src.storage.database import db
    session = db.get_session()
    try:
        count = cleanup_expired_tokens(session)
        return {"cleaned": count}
    finally:
        session.close()


@celery_app.task(name="src.pipeline.celery_app.check_price_alerts")
def check_price_alerts():
    """检查价格预警并推送 Telegram。"""
    import requests as _req
    try:
        r = _req.post("http://dashboard:8000/api/alerts/check", timeout=30)
        return r.json()
    except Exception:
        return {"error": "alert_check_failed"}
