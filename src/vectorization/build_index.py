"""构建推文向量索引。

本模块负责从数据库读取未向量化的推文，逐批调用 Embedder 生成向量，
写入 ChromaDB，并更新数据库中的向量化状态标记。

整体流程：
1. 查询数据库中 is_vectorized=False 的推文
2. 按 batch_size 分批处理
3. 每批：清洗文本 → 调用 embedder.embed_texts → 写入 Chroma →
   更新数据库标记 + 写入 VectorMetadata 记录

使用方式：
- 命令行直接运行: python src/vectorization/build_index.py
- 程序调用: IndexBuilder(limit=200).build()
"""
from __future__ import annotations

from datetime import datetime

from src.storage.database import db
from src.storage.models import Tweet, User, VectorMetadata
from src.utils.helpers import clean_text
from src.utils.logger import logger
from src.vectorization.embedder import OpenAIEmbedder
from src.vectorization.vector_store import ChromaVectorStore


class IndexBuilder:
    """把数据库中的未向量化推文写入 Chroma。

    特性：
    - 增量构建：只处理 is_vectorized=False 的记录
    - 批处理：按 batch_size 分批，避免一次性加载过多数据
    - 幂等：重复运行不会重复插入（已标记的不再处理）
    - 事务安全：每批提交一次，失败批次可重试
    """

    def __init__(self, batch_size: int = 100) -> None:
        """初始化索引构建器。

        Args:
            batch_size: 每批处理的推文数量。默认 100。
                        根据 API 调用成本和内存配置调整：
                        - 值越大，API 调用次数越少，但单次请求数据和内存占用越大
                        - 值越小，处理越细粒度，但 API 调用次数增多
        """
        self.batch_size = batch_size
        # 嵌入器：默认 OpenAIEmbedder，无 Key 时自动 HashEmbedder 回退
        self.embedder = OpenAIEmbedder()
        # 向量库：ChromaDB 持久化到 data/vector_db
        self.vector_store = ChromaVectorStore()
        # 初始化数据库连接
        db.init_db()

    def build(self, limit: int | None = None) -> int:
        """执行增量索引构建。

        处理流程：
        1. 查询未向量化的推文（按推文创建时间升序，优先处理旧推文）
        2. 按 batch_size 分批
        3. 每批内：
           a. 清洗推文文本（去除特殊字符、URL 等）
           b. 过滤掉清洗后为空的记录
           c. 调用 embedder 生成向量
           d. 组装 Chroma 需要的 ids/documents/embeddings/metadatas
           e. 写入 Chroma
           f. 更新 Tweet.is_vectorized=True + vectorized_at 时间戳
           g. 写入 VectorMetadata 记录（chunk 溯源信息）
        4. 提交事务，继续下一批

        Args:
            limit: 最大处理条数限制。None 表示处理全部未向量化推文。

        Returns:
            int: 本次实际处理并向量化的推文总数
        """
        session = db.get_session()
        total = 0
        try:
            # 查询未向量化的推文，按推文创建时间升序排列（先处理历史数据）
            query = session.query(Tweet).filter(
                Tweet.is_vectorized.is_(False)
            ).order_by(Tweet.created_at_twitter.asc())

            if limit:
                query = query.limit(limit)
            tweets = query.all()

            # 按 batch_size 分批处理
            for start in range(0, len(tweets), self.batch_size):
                batch = tweets[start : start + self.batch_size]

                # 清洗推文文本：去除 HTML、特殊字符、URL 等
                documents = [clean_text(tweet.text) for tweet in batch]
                # 过滤掉清洗后为空文本的记录
                valid_pairs = [
                    (tweet, doc) for tweet, doc in zip(batch, documents, strict=False) if doc
                ]
                if not valid_pairs:
                    continue

                # 组装 Chroma 写入数据
                ids = [f"tweet:{tweet.tweet_id}:0" for tweet, _ in valid_pairs]
                docs = [doc for _, doc in valid_pairs]
                # 调用 embedder 批量生成向量（单次 API 调用处理整批）
                embeddings = self.embedder.embed_texts(docs)

                # 组装元数据：每条推文附带作者信息、时间戳等
                metadatas = []
                for tweet, _ in valid_pairs:
                    user = session.query(User).filter(User.id == tweet.user_id).one()
                    metadatas.append(
                        {
                            "tweet_id": tweet.tweet_id,
                            "username": user.username,
                            "display_name": user.display_name or user.username,
                            "url": tweet.url,
                            "created_at": tweet.created_at_twitter.isoformat(),
                            "is_reply": tweet.is_reply,
                            "is_retweet": tweet.is_retweet,
                            "has_media": tweet.has_media,
                        }
                    )

                # 写入 Chroma 向量库
                self.vector_store.add(
                    ids=ids,
                    documents=docs,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )

                # 更新数据库：标记推文已向量化 + 写入 VectorMetadata 溯源记录
                for tweet, doc in valid_pairs:
                    tweet.is_vectorized = True
                    tweet.vectorized_at = datetime.now()
                    # VectorMetadata 记录 chunk 信息，便于后续溯源和重建
                    session.add(
                        VectorMetadata(
                            vector_id=f"tweet:{tweet.tweet_id}:0",
                            tweet_id=tweet.id,
                            chunk_index=0,
                            chunk_text=doc,
                        )
                    )

                # 提交当前批次事务
                session.commit()
                total += len(valid_pairs)
                logger.info(f"向量化批次完成: {len(valid_pairs)} 条")

        finally:
            session.close()

        logger.info(f"索引构建完成，共处理 {total} 条")
        return total


if __name__ == "__main__":
    IndexBuilder().build()
