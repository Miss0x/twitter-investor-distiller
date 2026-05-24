"""下载已入库的媒体文件到本地。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.storage.database import db
from src.storage.models import Media

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = PROJECT_ROOT / "data" / "media"
COOKIES_PATH = PROJECT_ROOT / "data" / "cookies.json"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    if COOKIES_PATH.exists():
        raw = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))
        for c in raw:
            session.cookies.set(c["name"], c.get("value", ""), domain=c.get("domain", ""))
    return session


def _url_to_filename(url: str) -> str:
    """从 URL 生成确定性的短文件名。"""
    # 取 URL 中 media/ 后面的部分
    parsed = urlparse(url)
    path = parsed.path
    # 提取 media/ 后的 key
    if "/media/" in path:
        key = path.split("/media/", 1)[1]
    else:
        key = path.rsplit("/", 1)[-1]
    # 去掉查询参数干扰
    key = key.split("?")[0].split("%3F")[0]
    # 短哈希防冲突
    url_hash = hashlib.md5(url.encode()).hexdigest()[:6]
    stem = Path(key).stem or "image"
    ext = Path(key).suffix or ".jpg"
    return f"{stem}_{url_hash}{ext}"


def download_all(limit: int | None = None, timeout: int = 30) -> dict:
    """下载所有未下载媒体。返回 {total, downloaded, skipped, failed}。"""
    session = _build_session()
    stats = {"total": 0, "downloaded": 0, "skipped": 0, "failed": 0}

    db_session = db.get_session()
    try:
        query = db_session.query(Media).filter(Media.downloaded == False)
        if limit:
            query = query.limit(limit)
        records = query.all()
        stats["total"] = len(records)

        for media in records:
            url = media.media_url
            if not url:
                stats["skipped"] += 1
                continue

            # 目标路径：data/media/<tweet_id>/<filename>
            target_dir = MEDIA_DIR / str(media.tweet_id)
            target_dir.mkdir(parents=True, exist_ok=True)
            filename = _url_to_filename(url)
            target_path = target_dir / filename

            if target_path.exists():
                media.downloaded = True
                media.local_path = str(target_path.relative_to(PROJECT_ROOT))
                media.download_error = None
                stats["skipped"] += 1
                continue

            try:
                resp = session.get(url, timeout=timeout, stream=True)
                resp.raise_for_status()
                with open(target_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                media.downloaded = True
                media.local_path = str(target_path.relative_to(PROJECT_ROOT))
                media.download_error = None
                stats["downloaded"] += 1
            except Exception as exc:
                media.downloaded = False
                media.download_error = str(exc)[:500]
                stats["failed"] += 1

        db_session.commit()
    finally:
        db_session.close()

    return stats


def main() -> None:
    db.init_db()
    print(f"开始下载媒体文件...")
    result = download_all()
    print(f"总计: {result['total']} | 已下载: {result['downloaded']} | 已存在: {result['skipped']} | 失败: {result['failed']}")


if __name__ == "__main__":
    main()
