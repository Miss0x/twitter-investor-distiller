"""检索模块。"""
from __future__ import annotations

from src.vectorization.embedder import OpenAIEmbedder
from src.vectorization.vector_store import ChromaVectorStore


class TweetRetriever:
    """基于用户问题检索相关推文。"""

    def __init__(self, embedder: OpenAIEmbedder | None = None, vector_store: ChromaVectorStore | None = None) -> None:
        self.embedder = embedder or OpenAIEmbedder()
        self.vector_store = vector_store or ChromaVectorStore()

    def retrieve(self, question: str, top_k: int = 5) -> list[dict]:
        embedding = self.embedder.embed_query(question)
        result = self.vector_store.query(embedding, top_k=top_k)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            {"text": doc, "metadata": meta, "distance": dist}
            for doc, meta, dist in zip(documents, metadatas, distances, strict=False)
        ]
