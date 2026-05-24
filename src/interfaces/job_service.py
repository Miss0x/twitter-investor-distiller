"""阶段 1/2/4：抓取任务服务层。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from src.storage.database import db
from src.storage.models import CrawlJob, CrawlJobCheckpoint, CrawlJobMode, CrawlJobStatus, CrawlJobType


ACTIVE_JOB_STATUSES = {CrawlJobStatus.RUNNING, CrawlJobStatus.STOPPING}
RECOVERABLE_JOB_STATUSES = {CrawlJobStatus.RUNNING, CrawlJobStatus.STOPPING}

ALLOWED_STATUS_TRANSITIONS: dict[CrawlJobStatus, set[CrawlJobStatus]] = {
    CrawlJobStatus.PENDING: {CrawlJobStatus.RUNNING, CrawlJobStatus.STOPPED},
    CrawlJobStatus.RUNNING: {
        CrawlJobStatus.PAUSED,
        CrawlJobStatus.STOPPING,
        CrawlJobStatus.COMPLETED,
        CrawlJobStatus.FAILED,
    },
    CrawlJobStatus.PAUSED: {CrawlJobStatus.RUNNING, CrawlJobStatus.STOPPING, CrawlJobStatus.STOPPED},
    CrawlJobStatus.STOPPING: {CrawlJobStatus.STOPPED, CrawlJobStatus.FAILED},
    CrawlJobStatus.STOPPED: set(),
    CrawlJobStatus.COMPLETED: set(),
    CrawlJobStatus.FAILED: set(),
}


class CrawlJobService:
    """管理抓取任务与断点。"""

    def create_job(
        self,
        usernames: list[str],
        mode: CrawlJobMode = CrawlJobMode.RECENT_3M,
        job_type: CrawlJobType = CrawlJobType.BACKFILL,
    ) -> CrawlJob:
        normalized_usernames = [item.lstrip("@").strip() for item in usernames if item.strip()]
        if not normalized_usernames:
            raise ValueError("创建任务时至少需要一个用户名")

        session = db.get_session()
        try:
            job = CrawlJob(
                job_type=job_type.value,
                status=CrawlJobStatus.PENDING.value,
                mode=mode.value,
                target_usernames=normalized_usernames,
                users_total=len(normalized_usernames),
                current_username=normalized_usernames[0],
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    def list_jobs(self) -> list[CrawlJob]:
        session = db.get_session()
        try:
            return session.query(CrawlJob).order_by(CrawlJob.created_at.desc(), CrawlJob.id.desc()).all()
        finally:
            session.close()

    def list_recoverable_jobs(self) -> list[CrawlJob]:
        session = db.get_session()
        try:
            return (
                session.query(CrawlJob)
                .filter(CrawlJob.status.in_([status.value for status in RECOVERABLE_JOB_STATUSES]))
                .order_by(CrawlJob.updated_at.asc(), CrawlJob.id.asc())
                .all()
            )
        finally:
            session.close()

    def get_job(self, job_id: int) -> CrawlJob | None:
        session = db.get_session()
        try:
            return session.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
        finally:
            session.close()

    def get_active_job(self) -> CrawlJob | None:
        session = db.get_session()
        try:
            return (
                session.query(CrawlJob)
                .filter(CrawlJob.status.in_([status.value for status in ACTIVE_JOB_STATUSES]))
                .order_by(CrawlJob.updated_at.asc(), CrawlJob.id.asc())
                .one_or_none()
            )
        finally:
            session.close()

    def ensure_no_other_active_job(self, job_id: int | None = None) -> None:
        active_job = self.get_active_job()
        if active_job is None:
            return
        if job_id is not None and active_job.id == job_id:
            return
        raise ValueError(f"已有活动任务正在运行: {active_job.id}")

    def transition_status(
        self,
        job_id: int,
        new_status: CrawlJobStatus,
        *,
        last_error: str | None = None,
    ) -> CrawlJob:
        session = db.get_session()
        try:
            job = session.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
            if job is None:
                raise ValueError(f"任务不存在: {job_id}")

            current_status = CrawlJobStatus(job.status)
            if new_status != current_status and new_status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
                raise ValueError(f"非法状态流转: {current_status.value} -> {new_status.value}")

            job.status = new_status.value
            job.last_error = last_error
            if new_status == CrawlJobStatus.RUNNING and not job.started_at:
                job.started_at = datetime.now()
            if new_status in {CrawlJobStatus.STOPPED, CrawlJobStatus.COMPLETED, CrawlJobStatus.FAILED}:
                job.finished_at = datetime.now()
            if new_status in {CrawlJobStatus.PENDING, CrawlJobStatus.RUNNING, CrawlJobStatus.PAUSED, CrawlJobStatus.STOPPING}:
                job.finished_at = None
            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    def request_pause(self, job_id: int) -> CrawlJob:
        return self.transition_status(job_id, CrawlJobStatus.PAUSED)

    def request_stop(self, job_id: int) -> CrawlJob:
        return self.transition_status(job_id, CrawlJobStatus.STOPPING)

    def restart_job(self, job_id: int) -> CrawlJob:
        """将终态任务重置为 PENDING，保留原有参数和 checkpoint。"""
        session = db.get_session()
        try:
            job = session.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
            if job is None:
                raise ValueError(f"任务不存在: {job_id}")

            current_status = CrawlJobStatus(job.status)
            if current_status not in (CrawlJobStatus.STOPPED, CrawlJobStatus.COMPLETED, CrawlJobStatus.FAILED):
                raise ValueError(f"只能重新开始已结束的任务，当前状态: {current_status.value}")

            job.status = CrawlJobStatus.PENDING.value
            job.last_error = None
            job.progress_percent = 0.0
            job.tweets_collected_total = 0
            job.users_completed = 0
            job.started_at = None
            job.finished_at = None
            # 重置为第一个用户名
            if job.target_usernames:
                job.current_username = job.target_usernames[0]

            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    def update_job_progress(
        self,
        job_id: int,
        *,
        current_username: str | None = None,
        progress_percent: float | None = None,
        tweets_collected_total: int | None = None,
        users_completed: int | None = None,
        last_error: str | None = None,
    ) -> CrawlJob:
        session = db.get_session()
        try:
            job = session.query(CrawlJob).filter(CrawlJob.id == job_id).one_or_none()
            if job is None:
                raise ValueError(f"任务不存在: {job_id}")

            if current_username is not None:
                job.current_username = current_username
            if progress_percent is not None:
                job.progress_percent = max(0.0, min(100.0, progress_percent))
            if tweets_collected_total is not None:
                job.tweets_collected_total = max(0, tweets_collected_total)
            if users_completed is not None:
                job.users_completed = max(0, users_completed)
            if last_error is not None:
                job.last_error = last_error

            session.commit()
            session.refresh(job)
            return job
        finally:
            session.close()

    def save_checkpoint(
        self,
        job_id: int,
        username: str,
        *,
        last_seen_tweet_id: str | None = None,
        last_seen_tweet_time: datetime | None = None,
        scroll_iterations: int | None = None,
        consecutive_no_new_items: int | None = None,
        tweets_collected: int | None = None,
        page_cursor: str | None = None,
        stats_json: dict[str, Any] | None = None,
    ) -> CrawlJobCheckpoint:
        normalized_username = username.lstrip("@").strip()
        if not normalized_username:
            raise ValueError("保存 checkpoint 时 username 不能为空")

        session = db.get_session()
        try:
            checkpoint = (
                session.query(CrawlJobCheckpoint)
                .filter(CrawlJobCheckpoint.job_id == job_id, CrawlJobCheckpoint.username == normalized_username)
                .one_or_none()
            )
            if checkpoint is None:
                checkpoint = CrawlJobCheckpoint(job_id=job_id, username=normalized_username)
                session.add(checkpoint)

            if last_seen_tweet_id is not None:
                checkpoint.last_seen_tweet_id = last_seen_tweet_id
            if last_seen_tweet_time is not None:
                checkpoint.last_seen_tweet_time = last_seen_tweet_time
            if scroll_iterations is not None:
                checkpoint.scroll_iterations = scroll_iterations
            if consecutive_no_new_items is not None:
                checkpoint.consecutive_no_new_items = consecutive_no_new_items
            if tweets_collected is not None:
                checkpoint.tweets_collected = tweets_collected
            if page_cursor is not None:
                checkpoint.page_cursor = page_cursor
            if stats_json is not None:
                checkpoint.stats_json = stats_json

            session.commit()
            session.refresh(checkpoint)
            return checkpoint
        finally:
            session.close()

    def get_checkpoint(self, job_id: int, username: str) -> CrawlJobCheckpoint | None:
        normalized_username = username.lstrip("@").strip()
        session = db.get_session()
        try:
            return (
                session.query(CrawlJobCheckpoint)
                .filter(CrawlJobCheckpoint.job_id == job_id, CrawlJobCheckpoint.username == normalized_username)
                .one_or_none()
            )
        finally:
            session.close()

    def list_checkpoints(self, job_id: int) -> list[CrawlJobCheckpoint]:
        session = db.get_session()
        try:
            return (
                session.query(CrawlJobCheckpoint)
                .filter(CrawlJobCheckpoint.job_id == job_id)
                .order_by(CrawlJobCheckpoint.updated_at.desc(), CrawlJobCheckpoint.id.desc())
                .all()
            )
        finally:
            session.close()
