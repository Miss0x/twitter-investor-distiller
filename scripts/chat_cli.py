"""命令行对话入口。"""
from __future__ import annotations

from src.ai.chat_engine import ChatEngine


def main() -> None:
    engine = ChatEngine()
    print("Twitter 用户蒸馏 AI 助手 CLI，输入 exit 退出。")
    while True:
        question = input("\n你：").strip()
        if question.lower() in {"exit", "quit", "q"}:
            break
        print("\n助手：")
        print(engine.answer(question))


if __name__ == "__main__":
    main()
