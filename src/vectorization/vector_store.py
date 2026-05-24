"""Chroma 向量数据库封装。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb


class ChromaVectorStore:
    """本地 Chroma 向量库。"""

    def __init__(self, persist_dir: str = "data/vector_db", collection_name: str = "tweets") -> None:
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add(self, ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict[str, Any]]) -> None:
        if not ids:
            return
        self.collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    def query(self, query_embedding: list[float], top_k: int = 5) -> dict[str, Any]:
        return self.collection.query(query_embeddings=[query_embedding], n_results=top_k)
