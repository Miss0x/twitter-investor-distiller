"""AI 对话引擎。"""
from __future__ import annotations

import os

from openai import OpenAI

from src.ai.prompts import DISTILL_SYSTEM_PROMPT, USER_PROMPT
from src.utils.env import load_project_env
from src.vectorization.retriever import TweetRetriever

load_project_env()



class ChatEngine:
    """RAG 对话引擎。"""

    def __init__(self, retriever: TweetRetriever | None = None, model: str | None = None) -> None:
        self.retriever = retriever or TweetRetriever()
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def answer(self, question: str, top_k: int = 5) -> str:
        references = self.retriever.retrieve(question, top_k=top_k)
        context = "\n\n".join(
            f"来源: {item['metadata']}\n内容: {item['text']}" for item in references
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": DISTILL_SYSTEM_PROMPT.format(context=context)},
                {"role": "user", "content": USER_PROMPT.format(question=question)},
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content or ""
