"""构建推文向量索引。"""
from __future__ import annotations

from datetime import datetime

from src.storage.database import db
from src.storage.models import Tweet, User, VectorMetadata
from src.utils.helpers import clean_text
from src.utils.logger import logger
from src.vectorization.embedder import OpenAIEmbedder
from src.vectorization.vector_store import ChromaVectorStore


class IndexBuilder:
    """把数据库中的未向量化推文写入 Chroma。"""

    def __init__(self, batch_size: int = 100) -> None:
        self.batch_size = batch_size
        self.embedder = OpenAIEmbedder()
        self.vector_store = ChromaVectorStore()
        db.init_db()

    def build(self, limit: int | None = None) -> int:
        session = db.get_session()
        total = 0
        try:
            query = session.query(Tweet).filter(Tweet.is_vectorized.is_(False)).order_by(Tweet.created_at_twitter.asc())
            if limit:
                query = query.limit(limit)
            tweets = query.all()

            for start in range(0, len(tweets), self.batch_size):
                batch = tweets[start : start + self.batch_size]
                documents = [clean_text(tweet.text) for tweet in batch]
                valid_pairs = [(tweet, doc) for tweet, doc in zip(batch, documents, strict=False) if doc]
                if not valid_pairs:
                    continue

                ids = [f"tweet:{tweet.tweet_id}:0" for tweet, _ in valid_pairs]
                docs = [doc for _, doc in valid_pairs]
                embeddings = self.embedder.embed_texts(docs)
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

                self.vector_store.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metadatas)

                for tweet, doc in valid_pairs:
                    tweet.is_vectorized = True
                    tweet.vectorized_at = datetime.now()
                    session.add(VectorMetadata(vector_id=f"tweet:{tweet.tweet_id}:0", tweet_id=tweet.id, chunk_index=0, chunk_text=doc))
                session.commit()
                total += len(valid_pairs)
                logger.info(f"向量化批次完成: {len(valid_pairs)} 条")
        finally:
            session.close()
        logger.info(f"索引构建完成，共处理 {total} 条")
        return total


if __name__ == "__main__":
    IndexBuilder().build()
