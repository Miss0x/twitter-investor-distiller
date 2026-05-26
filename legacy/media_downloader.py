"""媒体下载模块。"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests

from src.utils.logger import logger


class MediaDownloader:
    """下载并管理推文媒体文件。"""

    def __init__(self, base_dir: str | Path = "data/media", timeout: int = 60) -> None:
        self.base_dir = Path(base_dir)
        self.timeout = timeout
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def download(self, url: str, username: str, tweet_id: str, index: int = 0) -> Path | None:
        """下载单个媒体文件。"""
        try:
            suffix = self._infer_suffix(url)
            target_dir = self.base_dir / username / tweet_id
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"media_{index}{suffix}"

            if target_path.exists():
                logger.info(f"媒体已存在，跳过下载: {target_path}")
                return target_path

            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            target_path.write_bytes(response.content)
            logger.info(f"媒体下载完成: {target_path}")
            return target_path
        except Exception as exc:  # noqa: BLE001
            logger.error(f"媒体下载失败: {url} | {exc}")
            return None

    def _infer_suffix(self, url: str) -> str:
        path = urlparse(url).path.lower()
        for suffix in [".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webp"]:
            if suffix in path:
                return suffix
        return ".bin"
