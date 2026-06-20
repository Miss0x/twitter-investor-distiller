"""数据库索引回归测试。

背景：
- 2026-06-20 性能调优发现 3 处缺失索引，导致全表扫描：
  1. Tweet.is_vectorized + ORDER BY created_at_twitter
  2. Media.downloaded
  3. PipelineTask.task_type + status
- 本测试锁定修复：若未来重构移除这些索引，测试立刻失败。
"""
from __future__ import annotations

from sqlalchemy import Index

from src.storage.database import Base
from src.storage.models import Media, PipelineTask, Tweet


def _indexed_columns(table) -> set[tuple[str, ...]]:
    """收集一张表上所有索引的列组合（不含主键约束上的自动索引）。"""
    return {
        tuple(col.name for col in idx.columns)
        for idx in table.indexes
        if isinstance(idx, Index)
    }


def test_tweet_vec_pending_index_exists():
    """Tweet 上必须有 (is_vectorized, created_at_twitter) 复合索引。

    用途：向量批处理 worker 扫描未向量化推文，按时间升序排列。
    """
    indexed = _indexed_columns(Base.metadata.tables["tweets"])
    assert ("is_vectorized", "created_at_twitter") in indexed, (
        f"tweets 缺少 (is_vectorized, created_at_twitter) 复合索引；现有索引: {indexed}"
    )


def test_media_downloaded_index_exists():
    """Media 上必须有 downloaded 单列索引。

    用途：媒体下载 worker 扫描未下载文件。
    """
    indexed = _indexed_columns(Base.metadata.tables["media"])
    assert ("downloaded",) in indexed, (
        f"media 缺少 downloaded 索引；现有索引: {indexed}"
    )


def test_pipeline_tasks_type_status_index_exists():
    """PipelineTask 上必须有 (task_type, status) 复合索引。

    用途：Pipeline API 的 WHERE task_type = ? AND status = ? 筛选 + ORDER BY id DESC。
    """
    indexed = _indexed_columns(Base.metadata.tables["pipeline_tasks"])
    assert ("task_type", "status") in indexed, (
        f"pipeline_tasks 缺少 (task_type, status) 复合索引；现有索引: {indexed}"
    )


def test_existing_indexes_preserved():
    """现有索引不能被破坏：Tweet(user_id, created_at_twitter) 联合索引必须保留。"""
    indexed = _indexed_columns(Base.metadata.tables["tweets"])
    assert ("user_id", "created_at_twitter") in indexed, (
        f"tweets 缺少原有的 (user_id, created_at_twitter) 索引；现有索引: {indexed}"
    )


def test_model_classes_have_table_args():
    """三个表都显式声明了 __table_args__，作为未来索引扩展点。"""
    assert hasattr(Tweet, "__table_args__"), "Tweet 缺少 __table_args__"
    assert hasattr(Media, "__table_args__"), "Media 缺少 __table_args__"
    assert hasattr(PipelineTask, "__table_args__"), "PipelineTask 缺少 __table_args__"