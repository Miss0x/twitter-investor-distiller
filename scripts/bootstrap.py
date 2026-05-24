"""项目初始化脚本。"""
from __future__ import annotations

from pathlib import Path

from src.storage.database import init_database


def main() -> None:
    for path in ["data/raw", "data/processed", "data/media", "data/vector_db", "logs"]:
        Path(path).mkdir(parents=True, exist_ok=True)
    init_database()
    print("初始化完成。下一步：复制 config/.env.example 为 config/.env，并填写 OPENAI_API_KEY。")


if __name__ == "__main__":
    main()
