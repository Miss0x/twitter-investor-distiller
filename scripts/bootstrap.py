"""项目初始化脚本。

功能：
1. 创建项目所需的目录结构（data/raw, data/processed, data/media, data/vector_db, logs）
2. 初始化 SQLite 数据库（创建所有表结构）

这是运行整个项目的第一步，确保后续的数据采集、处理、分析流水线
都有正确的文件存储路径和数据库结构。

使用方式：
    python scripts/bootstrap.py

初始化完成后，还需要：
- 复制 config/.env.example 为 config/.env
- 填写 OPENAI_API_KEY（用于 LLM 分析 + 向量化）
"""
from __future__ import annotations

from pathlib import Path

from src.storage.database import init_database


def main() -> None:
    """执行项目初始化。

    步骤：
    1. 创建 data/ 子目录：raw（原始抓取数据）、processed（处理后数据）、
       media（下载的媒体文件）、vector_db（ChromaDB 持久化数据）
    2. 创建 logs/ 目录：存放运行日志
    3. 调用 init_database() 创建 SQLite 表结构（Users, Tweets, PipelineTasks 等）
    4. 输出初始化完成提示和下一步指引
    """
    # 创建必需的目录结构（exist_ok=True 表示已存在不报错）
    for path in ["data/raw", "data/processed", "data/media", "data/vector_db", "logs"]:
        Path(path).mkdir(parents=True, exist_ok=True)

    # 初始化数据库（创建所有表、索引）
    init_database()

    # 输出下一步操作指引
    print("初始化完成。下一步：复制 config/.env.example 为 config/.env，并填写 OPENAI_API_KEY。")


if __name__ == "__main__":
    main()
