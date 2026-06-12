"""
RAG 对话引擎
===========
电报机器人和 Web ChatBot 的后端。工作流程：
1. 用户提问 → 向量检索相关推文（TweetRetriever）
2. 将检索到的推文作为上下文注入 system prompt
3. 调用 LLM 生成基于推文内容的回答

这种"检索增强生成"（RAG）方式让 AI 能基于具体推文数据回答，
而不是凭空编造。每条回答都会附带引用来源。
"""

from __future__ import annotations

import os

from openai import OpenAI

from src.ai.prompts import DISTILL_SYSTEM_PROMPT, USER_PROMPT
from src.governance.context_provider import build_governance_context, is_investment_judgment_question
from src.utils.env import load_project_env
from src.vectorization.retriever import TweetRetriever

# ── 加载 .env 环境变量（LLM_API_KEY / LLM_BASE_URL / CHAT_MODEL 等）──
load_project_env()


class ChatEngine:
    """
    RAG 对话引擎。
    
    组合了向量检索（TweetRetriever）+ OpenAI-compatible LLM 对话，
    用"检索到的推文"作为对话上下文，让 AI 的回答有据可依。
    
    Usage:
        engine = ChatEngine()
        answer = engine.answer("TJ_Research 最近怎么看 NVDA？")
    """

    def __init__(self, retriever: TweetRetriever | None = None, model: str | None = None) -> None:
        """
        Args:
            retriever: 推文检索器实例，不传则自动创建（连接 Chroma 向量库）
            model: 聊天模型名，不传则优先读取 CHAT_MODEL，兼容 OPENAI_MODEL
        """
        self.retriever = retriever or TweetRetriever()
        self.model = model or os.getenv("CHAT_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4-turbo-preview"
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def answer(self, question: str, top_k: int = 5) -> str:
        """
        回答用户问题（核心方法）。
        
        步骤：
        1. 向量检索 top_k 条最相关的推文
        2. 构建上下文（来源 + 内容）
        3. 调用 LLM 生成回答
        
        Args:
            question: 用户自然语言问题
            top_k: 检索的推文数量（默认 5 条）
        
        Returns:
            str: AI 生成的回答文本
        """
        # Step 1: 向量检索
        references = self.retriever.retrieve(question, top_k=top_k)
        # Step 2: 拼接上下文
        tweet_context = "\n\n".join(
            f"来源: {item['metadata']}\n内容: {item['text']}" for item in references
        )
        if is_investment_judgment_question(question):
            governance_context = build_governance_context(question)
            context = f"治理信号上下文:\n{governance_context}\n\n原始推文上下文:\n{tweet_context}"
        else:
            context = tweet_context
        # Step 3: LLM 生成回答
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": DISTILL_SYSTEM_PROMPT.format(context=context)},
                {"role": "user", "content": USER_PROMPT.format(question=question)},
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content or ""
