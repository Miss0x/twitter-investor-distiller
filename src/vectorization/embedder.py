"""文本向量化模块。

本模块提供两种文本嵌入器：
- OpenAIEmbedder：调用 OpenAI text-embedding-3-small 等模型生成语义向量
- HashEmbedder：基于 SHA256-hash 的本地伪随机向量生成器
  用于无 API Key 时打通"入库 -> 建索引 -> 检索"的开发链路

生产环境推荐使用 OpenAIEmbedder 或切换至 BGE-M3 / text2vec 等开源方案。
"""
from __future__ import annotations

import hashlib
import math
import os

from openai import OpenAI

from src.utils.env import load_project_env

# 加载项目环境变量（.env 文件中的 OPENAI_API_KEY 等配置）
load_project_env()


class HashEmbedder:
    """本地 Hash 向量化器。

    核心思路：对文本中的每个 token 做 SHA256 哈希，将哈希值的部分字节
    映射到向量维度索引上做 +/- 累加，最后 L2 归一化。

    优点：
    - 无需任何 API Key，纯本地运行
    - 相同的文本总是产生相同的向量（确定性）
    - 可快速验证全链路是否跑通

    缺点：
    - 语义值为零：语义相近的文本不会产生相近的向量
    - 不适合生产环境的语义检索
    """

    def __init__(self, dimensions: int = 384) -> None:
        """初始化 Hash 嵌入器。

        Args:
            dimensions: 输出向量的维度数。默认 384，与 text-embedding-3-small 一致。
                       实际使用时会覆盖为 OpenAI 的维度配置。
        """
        self.dimensions = dimensions
        import logging
        logging.getLogger(__name__).warning(
            "HashEmbedder 已激活 — 生成伪随机向量，语义值为零。"
            "生产环境请设置 OPENAI_API_KEY 使用 OpenAIEmbedder。"
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化。

        Args:
            texts: 待向量化的文本列表

        Returns:
            list[list[float]]: 与输入一一对应的向量列表，每个向量长度为 dimensions
        """
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """单条查询文本向量化（embed_texts 的单条便捷包装）。

        Args:
            text: 查询文本

        Returns:
            list[float]: 长度为 dimensions 的向量
        """
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        """核心哈希向量化算法。

        算法步骤：
        1. 初始化 dimensions 维的零向量
        2. 将文本转小写、替换换行、按空格分词
        3. 对每个 token 做 SHA256 哈希
        4. 取哈希前 4 字节作为索引（模 dimensions）
        5. 取哈希第 5 字节奇偶决定该维度 +/- 1
        6. 对所有 token 累加后 L2 归一化

        注意：此向量无语义信息，相同 token 会聚拢到同一维度，但维度冲突是不可避免的。

        Args:
            text: 输入文本

        Returns:
            list[float]: 归一化后的哈希向量
        """
        vector = [0.0] * self.dimensions
        # 预处理：转小写 + 替换换行为空格 + 按空格拆分 token
        tokens = [token for token in text.lower().replace("\n", " ").split(" ") if token]
        for token in tokens:
            # SHA256 哈希
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # 前 4 字节转为无符号整数，模 dimensions 确定维度索引
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            # 第 5 字节奇偶决定正负方向
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        # L2 归一化：确保向量长度为 1（便于余弦相似度计算）
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class OpenAIEmbedder:
    """OpenAI Embeddings 封装。

    功能：
    - 调用 OpenAI text-embedding-3-small / text-embedding-3-large 等模型
    - 缺少有效 API Key 时自动回退到本地 HashEmbedder
    - batch 模式下一次 API 调用处理多条文本，提升效率

    配置：
    - OPENAI_API_KEY: 环境变量或 .env 文件中设置
    - EMBEDDING_MODEL: 环境变量指定模型名，默认为 text-embedding-3-small
    """

    def __init__(self, model: str | None = None) -> None:
        """初始化 OpenAI 嵌入器。

        Args:
            model: OpenAI embedding 模型名。若不指定，从环境变量 EMBEDDING_MODEL 读取，
                   默认为 text-embedding-3-small。
                   可选值：text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002

        初始化逻辑：
        - 检查 OPENAI_API_KEY 是否有效（排除占位符 "your_" 开头）
        - 有效则创建 OpenAI client，无效则 client 为 None（后续调用自动触发 Hash 回退）
        """
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        # HashEmbedder 作为 fallback，确保无 API Key 也能正常运行
        self.fallback = HashEmbedder()
        self.client = None
        # 只在实际配置了有效 Key 时才初始化 OpenAI 客户端
        if self.api_key and not self.api_key.startswith("your_"):
            self.client = OpenAI(api_key=self.api_key)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化。

        策略：
        - 空列表直接返回空
        - 无有效 API Key 时自动回退 HashEmbedder
        - 有 API Key 时调用 OpenAI API，batch 内所有文本一次请求完成

        Args:
            texts: 待向量化的文本列表

        Returns:
            list[list[float]]: 与输入一一对应的向量列表
        """
        if not texts:
            return []
        # 回退逻辑：无 API 客户端时使用本地 Hash 向量
        if self.client is None:
            return self.fallback.embed_texts(texts)
        # 调用 OpenAI Embeddings API（单次请求批量处理）
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        """单条查询文本向量化。

        查询时复用 embed_texts，但只返回第一个向量。
        注意：对于单个文本，OpenAI 的 single 模式理论上有轻微性能差异，
        但实际影响可忽略。

        Args:
            text: 查询文本

        Returns:
            list[float]: 向量
        """
        return self.embed_texts([text])[0]
