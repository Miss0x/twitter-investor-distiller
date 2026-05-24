"""阶段 2/3：后台任务执行器。"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from src.crawler.browser_human_scraper import BrowserHumanScraper
from src.crawler.progress_tracker import ProgressTracker
from src.interfaces.job_service import CrawlJobService
from src.storage.models import CrawlJobStatus
from src.utils.logger import logger

TIMING_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "timing.yaml"


def _load_timing_config() -> dict:
    """从 YAML 配置读取当前 timing 参数。"""
    try:
        import yaml
    except ImportError:
        return {}
    if TIMING_CONFIG_PATH.exists():
        with open(TIMING_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("active", {}) if data else {}
    return {}


def _generate_monthly_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """生成 (since, until) 月度窗口，从 start 到 end。"""
    windows: list[tuple[datetime, datetime]] = []
    current = start.replace(day=1)
    while current <= end:
        if current.month == 12:
            next_month = current.replace(year=current.year + 1, month=1, day=1)
        else:
            next_month = current.replace(month=current.month + 1, day=1)
        until = min(next_month - timedelta(days=1), end)
        windows.append((current.replace(hour=0, minute=0, second=0, microsecond=0), until))
        current = next_month
    return windows


class JobRunner:
    """单进程单活动任务执行器。"""

    def __init__(
        self,
        job_service: CrawlJobService | None = None,
        tracker: ProgressTracker | None = None,
    ) -> None:
        self.job_service = job_service or CrawlJobService()
        self.tracker = tracker or ProgressTracker(self.job_service)
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._active_job_id: int | None = None

    def _build_scraper(self) -> BrowserHumanScraper:
        cfg = _load_timing_config()
        return BrowserHumanScraper(
            headless=True,
            max_scroll_rounds=cfg.get("max_scroll_rounds", 200),
            no_new_items_limit=cfg.get("no_new_items_limit", 10),
            minimum_created_at=datetime.fromisoformat(cfg.get("minimum_created_at", "2025-01-01")),
            page_ready_timeout_seconds=cfg.get("page_ready_timeout_seconds", 180),
            settle_after_scroll_ms=cfg.get("settle_after_scroll_ms", 3000),
        )

    def get_active_job_id(self) -> int | None:
        with self._lock:
            return self._active_job_id

    def is_job_running(self, job_id: int) -> bool:
        with self._lock:
            return self._active_job_id == job_id and self._worker_thread is not None and self._worker_thread.is_alive()

    def start_job(self, job_id: int) -> None:
        self._launch_job(job_id, allow_resume=False)

    def resume_job(self, job_id: int) -> None:
        self._launch_job(job_id, allow_resume=True)

    def recover_interrupted_jobs(self) -> list[int]:
        recovered: list[int] = []
        for job in self.job_service.list_recoverable_jobs():
            if self.get_active_job_id() is not None:
                break
            try:
                logger.info(f"开始恢复中断任务: {job.id}")
                self.resume_job(job.id)
                recovered.append(job.id)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"恢复任务失败 job_id={job.id}: {exc}")
        return recovered

    def wait_for_job(self, job_id: int, timeout: float | None = None) -> bool:
        thread = None
        with self._lock:
            if self._active_job_id == job_id:
                thread = self._worker_thread
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _launch_job(self, job_id: int, *, allow_resume: bool) -> None:
        with self._lock:
            if self._worker_thread is not None and not self._worker_thread.is_alive():
                self._worker_thread = None
                self._active_job_id = None

            job = self.tracker.get_job(job_id)
            status = CrawlJobStatus(job.status)

            if self._worker_thread is not None and self._worker_thread.is_alive():
                if allow_resume and self._active_job_id == job_id and status in {CrawlJobStatus.PAUSED, CrawlJobStatus.STOPPING}:
                    self._worker_thread.join(timeout=self.step_sleep_seconds * 2)
                    if self._worker_thread is not None and not self._worker_thread.is_alive():
                        self._worker_thread = None
                        self._active_job_id = None
                if self._worker_thread is not None and self._worker_thread.is_alive():
                    raise ValueError(f"已有任务正在执行: {self._active_job_id}")

            self.job_service.ensure_no_other_active_job(job_id=job_id if allow_resume else None)
            status = CrawlJobStatus(self.tracker.get_job(job_id).status)
            if allow_resume:
                if status not in {CrawlJobStatus.PAUSED, CrawlJobStatus.RUNNING, CrawlJobStatus.STOPPING}:
                    raise ValueError(f"当前状态不允许恢复: {status.value}")
            else:
                if status != CrawlJobStatus.PENDING:
                    raise ValueError(f"当前状态不允许启动: {status.value}")

            self.job_service.transition_status(job_id, CrawlJobStatus.RUNNING)
            thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
            self._worker_thread = thread
            self._active_job_id = job_id
            thread.start()

    def _run_job(self, job_id: int) -> None:
        try:
            job = self.tracker.get_job(job_id)
            self._run_browser_job(job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"任务执行失败 job_id={job_id}: {exc}")
            self.job_service.transition_status(job_id, CrawlJobStatus.FAILED, last_error=str(exc))
        finally:
            with self._lock:
                if self._active_job_id == job_id:
                    self._active_job_id = None
                    self._worker_thread = None

    def _run_browser_job(self, job_id: int) -> None:
        job = self.tracker.get_job(job_id)
        usernames = job.target_usernames or []
        if not usernames:
            raise ValueError("任务没有目标用户名")

        mode = job.mode
        if mode == "full_history":
            self._run_full_history_with_search(job_id, job, usernames)
        else:
            self._run_user_scroll_job(job_id, job, usernames)

    def _run_user_scroll_job(self, job_id: int, job, usernames: list[str]) -> None:
        """原有滚动模式：/with_replies + 无限滚动。"""
        tweets_collected_total = job.tweets_collected_total or 0
        users_completed = job.users_completed or 0
        start_index = users_completed
        if job.current_username and job.current_username in usernames:
            start_index = max(start_index, usernames.index(job.current_username))

        for user_index in range(start_index, len(usernames)):
            username = usernames[user_index]
            self.job_service.update_job_progress(job_id, current_username=username)
            control_status = self.tracker.get_control_status(job_id)
            if control_status == CrawlJobStatus.PAUSED:
                return
            if control_status == CrawlJobStatus.STOPPING:
                self.job_service.transition_status(job_id, CrawlJobStatus.STOPPED)
                return

            checkpoint = self.tracker.get_checkpoint(job_id, username)
            scraper = self._build_scraper()
            batch_result = scraper.crawl_user_recent(username, checkpoint=checkpoint)
            persisted = self.tracker.persist_scraped_tweets(
                job_id,
                username=username,
                tweets=batch_result.tweets,
                scroll_iterations=batch_result.scroll_iterations,
                consecutive_no_new_items=batch_result.consecutive_no_new_items,
                users_completed=users_completed,
                stats_json={
                    "mode": "browser_human",
                    "reached_time_limit": batch_result.reached_time_limit,
                    "oldest_tweet_time": batch_result.oldest_tweet_time.isoformat() if batch_result.oldest_tweet_time else None,
                    "batch_count": len(batch_result.tweets),
                },
            )
            tweets_collected_total = persisted.tweets_collected_total
            users_completed += 1
            self.tracker.mark_user_completed(
                job_id,
                username=username,
                tweets_collected_total=tweets_collected_total,
                users_completed=users_completed,
            )

            control_status = self.tracker.get_control_status(job_id)
            if control_status == CrawlJobStatus.PAUSED:
                logger.info(f"任务在浏览器抓取后暂停 job_id={job_id}")
                return
            if control_status == CrawlJobStatus.STOPPING:
                logger.info(f"任务在浏览器抓取后停止 job_id={job_id}")
                self.job_service.transition_status(job_id, CrawlJobStatus.STOPPED)
                return

        self.job_service.transition_status(job_id, CrawlJobStatus.COMPLETED)
        logger.info(f"浏览器任务执行完成 job_id={job_id}")

    def _run_full_history_with_search(self, job_id: int, job, usernames: list[str]) -> None:
        """full_history 模式：按月窗口 from:USER since:YYYY-MM until:YYYY-MM 搜索。"""
        tweets_collected_total = job.tweets_collected_total or 0
        users_completed = job.users_completed or 0
        start_index = users_completed
        if job.current_username and job.current_username in usernames:
            start_index = max(start_index, usernames.index(job.current_username))

        total_users = len(usernames)
        history_from = datetime.fromisoformat(cfg.get("history_from", "2025-01-01"))
        windows = _generate_monthly_windows(history_from, datetime.now())
        total_windows = len(windows)
        logger.info(f"full_history 模式: {total_windows} 个月度窗口, {total_users} 个用户")

        for user_index in range(start_index, total_users):
            username = usernames[user_index]
            self.job_service.update_job_progress(job_id, current_username=username)

            # --- 恢复窗口位置 ---
            checkpoint = self.tracker.get_checkpoint(job_id, username)
            window_index = 0
            if checkpoint and checkpoint.page_cursor:
                try:
                    window_index = int(json.loads(checkpoint.page_cursor).get("window_index", 0))
                except (json.JSONDecodeError, ValueError):
                    window_index = 0

            logger.info(f"@{username}: 从窗口 {window_index + 1}/{total_windows} 开始")
            for wi in range(window_index, total_windows):
                since, until = windows[wi]

                # --- 控制检查 ---
                control_status = self.tracker.get_control_status(job_id)
                if control_status == CrawlJobStatus.PAUSED:
                    self._save_window_checkpoint(job_id, username, wi, tweets_collected_total)
                    logger.info(f"@{username} 窗口 {wi + 1}/{total_windows} 暂停")
                    return
                if control_status == CrawlJobStatus.STOPPING:
                    self._save_window_checkpoint(job_id, username, wi, tweets_collected_total)
                    self.job_service.transition_status(job_id, CrawlJobStatus.STOPPED)
                    logger.info(f"@{username} 窗口 {wi + 1}/{total_windows} 停止")
                    return

                # --- 抓取本窗口 ---
                scraper = self._build_scraper()
                try:
                    batch_result = scraper.crawl_user_search_window(username, since, until)
                except Exception as exc:
                    logger.warning(f"@{username} 窗口 [{since.date()}~{until.date()}] 抓取异常: {exc}")
                    # 继续下一窗口，不因单月失败中断全流程
                    self._save_window_checkpoint(job_id, username, wi + 1, tweets_collected_total)
                    continue

                if batch_result.tweets:
                    persisted = self.tracker.persist_scraped_tweets(
                        job_id,
                        username=username,
                        tweets=batch_result.tweets,
                        scroll_iterations=batch_result.scroll_iterations,
                        consecutive_no_new_items=batch_result.consecutive_no_new_items,
                        users_completed=users_completed,
                        stats_json={
                            "mode": "search_window",
                            "window_since": since.isoformat(),
                            "window_until": until.isoformat(),
                            "reached_time_limit": batch_result.reached_time_limit,
                            "oldest_tweet_time": batch_result.oldest_tweet_time.isoformat() if batch_result.oldest_tweet_time else None,
                            "batch_count": len(batch_result.tweets),
                        },
                    )
                    tweets_collected_total = persisted.tweets_collected_total
                    logger.info(f"@{username} 窗口 [{since.date()}~{until.date()}]: +{len(batch_result.tweets)} 条 "
                                f"(总计 {tweets_collected_total}), {batch_result.scroll_iterations} 轮滚动")
                else:
                    logger.info(f"@{username} 窗口 [{since.date()}~{until.date()}]: 无新内容")

                # --- 保存窗口进度 ---
                self._save_window_checkpoint(job_id, username, wi + 1, tweets_collected_total)

                # --- 更新整体进度 ---
                user_progress = (user_index * total_windows + wi + 1) / (total_users * total_windows)
                self.job_service.update_job_progress(
                    job_id,
                    progress_percent=min(user_progress * 100, 99.0),
                    tweets_collected_total=tweets_collected_total,
                )

                # --- 窗口间冷却避免频率限制 ---
                time.sleep(2)

            users_completed += 1
            self.tracker.mark_user_completed(
                job_id,
                username=username,
                tweets_collected_total=tweets_collected_total,
                users_completed=users_completed,
            )
            logger.info(f"@{username} 全窗口完成，累计 {tweets_collected_total} 条推文")

        self.job_service.transition_status(job_id, CrawlJobStatus.COMPLETED)
        logger.info(f"full_history 浏览器任务完成 job_id={job_id}")

    def _save_window_checkpoint(self, job_id: int, username: str, window_index: int, tweets_collected_total: int) -> None:
        """保存搜索窗口断点（page_cursor 存 JSON 窗口索引）。"""
        self.job_service.save_checkpoint(
            job_id,
            username=username,
            page_cursor=json.dumps({"window_index": window_index}),
            tweets_collected=tweets_collected_total,
        )
