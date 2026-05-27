"""检索模块。

将用户自然语言问题向量化，在 ChromaDB 中检索语义最相似的推文。
这是 RAG（检索增强生成）流水线的检索环节——后续可将检索结果
注入 LLM prompt 中，让模型基于真实推文信息回答问题。
"""
from __future__ import annotations

from src.vectorization.embedder import OpenAIEmbedder
from src.vectorization.vector_store import ChromaVectorStore


class TweetRetriever:
    """基于用户问题检索相关推文。

    工作流程：
    1. 接收用户自然语言问题（如 "特斯拉最近有什么分析？"）
    2. 通过 embedder 将问题转换为向量
    3. 在 vector_store 中检索 top_k 最相似的推文向量
    4. 组装并返回结构化结果（文本 + 元数据 + 距离）

    依赖：
    - embedder: 提供文本到向量的转换（默认 OpenAIEmbedder，含 Hash 回退）
    - vector_store: 提供向量存储和检索（ChromaDB 持久化）
    """

    def __init__(
        self,
        embedder: OpenAIEmbedder | None = None,
        vector_store: ChromaVectorStore | None = None,
    ) -> None:
        """初始化检索器。

        Args:
            embedder: 文本嵌入器。可选，默认创建 OpenAIEmbedder 实例。
            vector_store: 向量库。可选，默认创建 ChromaVectorStore 实例。
                         如需自定义持久化路径，请在外部构建后传入。
        """
        self.embedder = embedder or OpenAIEmbedder()
        self.vector_store = vector_store or ChromaVectorStore()

    def retrieve(self, question: str, top_k: int = 5) -> list[dict]:
        """检索与问题最相关的推文。

        步骤：
        1. 将问题文本向量化
        2. 在向量库中查询 top_k 最相似推文
        3. 提取 Chroma 返回结果中的 documents（文本）、metadatas（元数据）、
           distances（余弦距离）
        4. 组装为 [{text, metadata, distance}, ...] 的列表格式

        Args:
            question: 用户的自然语言问题
            top_k: 检索结果数量，默认 5

        Returns:
            list[dict]: 检索结果列表，每条包含：
                - text (str): 推文清洗后的文本
                - metadata (dict): 元数据（username, created_at, tweet_id, url 等）
                - distance (float): 余弦距离，越小越相似
        """
        # 步骤 1：问题向量化
        embedding = self.embedder.embed_query(question)
        # 步骤 2：向量检索
        result = self.vector_store.query(embedding, top_k=top_k)
        # 步骤 3：提取 Chroma 返回结果
        # 注意：query 返回的是二维列表，第一维对应查询数（此处为1）
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        # 步骤 4：组装统一格式
        return [
            {"text": doc, "metadata": meta, "distance": dist}
            for doc, meta, dist in zip(documents, metadatas, distances, strict=False)
        ]
