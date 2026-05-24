"""文本向量化模块。"""
from __future__ import annotations

import hashlib
import math
import os

from openai import OpenAI

from src.utils.env import load_project_env

load_project_env()


class HashEmbedder:
    """本地 Hash 向量化器。

    用于没有 API Key 时打通“入库 -> 建索引 -> 检索”的开发链路。
    生产使用时建议切换到 OpenAI 或 BGE-M3 等真实语义向量模型。
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token for token in text.lower().replace("\n", " ").split(" ") if token]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class OpenAIEmbedder:
    """OpenAI Embeddings 封装，缺少有效 API Key 时自动回退本地 Hash 向量。"""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.fallback = HashEmbedder()
        self.client = None
        if self.api_key and not self.api_key.startswith("your_"):
            self.client = OpenAI(api_key=self.api_key)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.client is None:
            return self.fallback.embed_texts(texts)
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

