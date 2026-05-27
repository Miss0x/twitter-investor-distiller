"""
投资风格蒸馏模块
===============
从数据库中的原始推文数据提取用户的统计学特征，
生成基础画像（不依赖 LLM 分析结果）。

这个模块用于快速了解一个投资者的基本特征：
- 发推数量
- 回复/媒体比例（衡量互动性和内容类型）
- 平均推文长度（衡量信息密度）
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from src.storage.models import Tweet, User


class StyleDistiller:
    """
    从历史内容中提取用户风格画像。
    
    与 pipeline/task_executor.py 中的 LLM 画像生成（_generate_portrait）不同，
    这个模块只做纯统计，不调用 AI，速度极快。
    可作为 LLM 画像的补充或 fallback。
    
    Usage:
        distiller = StyleDistiller()
        profile = distiller.build_basic_profile(session, "TJ_Research")
    """

    def build_basic_profile(self, session: Session, username: str) -> dict:
        """
        构建用户的基础统计画像。
        
        Args:
            session: SQLAlchemy 数据库会话
            username: Twitter 用户名（可带或不带 @）
        
        Returns:
            dict: 包含以下字段的画像字典
                - username: Twitter 用户名
                - display_name: 显示名称
                - description: 个人简介
                - tweet_count: 推文总数
                - reply_ratio: 回复比例（衡量互动倾向）
                - media_ratio: 带媒体推文比例（衡量视觉内容偏好）
                - avg_text_length: 平均推文长度（衡量信息密度）
                或 {"error": "user not found"} 如果用户不存在
        """
        # 查找用户（自动去除 @ 前缀）
        user = session.query(User).filter(User.username == username.lstrip("@")).one_or_none()
        if not user:
            return {"error": "user not found"}

        # 获取该用户的所有推文
        tweets = session.query(Tweet).filter(Tweet.user_id == user.id).all()
        total = len(tweets)
        reply_count = sum(1 for t in tweets if t.is_reply)
        media_count = sum(1 for t in tweets if t.has_media)
        avg_length = sum(len(t.text or "") for t in tweets) / total if total else 0

        return {
            "username": user.username,
            "display_name": user.display_name,
            "description": user.description,
            "tweet_count": total,
            "reply_ratio": reply_count / total if total else 0,
            "media_ratio": media_count / total if total else 0,
            "avg_text_length": avg_length,
        }
