"""Chroma 向量数据库封装。

本模块封装了 ChromaDB 的持久化客户端，提供向量存储和检索的基础能力。
ChromaDB 是一个轻量级的开源向量数据库，基于 SQLite 本地持久化，
非常适合单机开发和原型验证场景。

存储内容：
- ids: 唯一标识符，格式为 "tweet:{tweet_id}:{chunk_index}"
- documents: 原始推文文本
- embeddings: 向量化后的嵌入表示
- metadatas: 附加元数据（用户名、时间戳、是否转发等）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb


class ChromaVectorStore:
    """本地 Chroma 向量库。

    使用 ChromaDB 的 PersistentClient 将数据持久化到本地磁盘。
    同一 collection 中的向量可以进行相似度检索（默认余弦距离）。

    使用模式：
    1. add(): 批量写入向量和元数据
    2. query(): 给定查询向量，返回 top_k 最相似的文档
    """

    def __init__(self, persist_dir: str = "data/vector_db", collection_name: str = "tweets") -> None:
        """初始化 Chroma 向量库。

        Args:
            persist_dir: 持久化目录路径，Chroma 的 SQLite 数据和索引文件均存储于此。
                         目录不存在时会自动创建。
            collection_name: 集合名称，不同集合之间向量互不干扰。
                             默认 "tweets"，所有推文使用同一集合。
        """
        # 确保持久化目录存在
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        # 创建持久化客户端（基于 SQLite）
        self.client = chromadb.PersistentClient(path=persist_dir)
        # 获取或创建集合：已存在则复用，不存在则新建
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """批量添加向量记录。

        所有列表长度必须一致，每次调用的数据作为一个批次写入 Chroma。
        由于 Chroma 使用 HNSW 索引，批量写入比逐条写入效率高得多。

        Args:
            ids: 每条记录的唯一标识符列表，格式为 "tweet:{tweet_id}:{chunk_index}"
            documents: 原始文本列表（推文清洗后的文本）
            embeddings: 向量列表，每个向量是 float 列表，维度需与索引一致
            metadatas: 元数据字典列表，包含 tweet_id, username, created_at 等字段
        """
        if not ids:
            return
        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(self, query_embedding: list[float], top_k: int = 5) -> dict[str, Any]:
        """向量相似度检索。

        使用余弦距离（Chroma 默认）在集合中查找与查询向量最相似的 top_k 条记录。

        返回值结构：
        {
            "ids": [["id1", "id2", ...]],       # 二维列表，第一维是查询数（此处为1）
            "documents": [["text1", ...]],
            "metadatas": [[{...}, ...]],
            "distances": [[0.1, 0.3, ...]],     # 距离值，越小越相似
        }

        Args:
            query_embedding: 查询文本的向量表示
            top_k: 返回的最相似结果数，默认 5

        Returns:
            dict: Chroma 标准查询结果字典，包含 ids/documents/metadatas/distances 四个字段
        """
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )
