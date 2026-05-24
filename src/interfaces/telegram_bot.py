"""Telegram Bot 接口。"""
from __future__ import annotations

import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.ai.chat_engine import ChatEngine
from src.utils.env import load_project_env

load_project_env()



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("欢迎使用 Twitter 用户蒸馏 AI 助手。直接发送问题即可开始。")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("你可以问：某个标的怎么看？某个叙事这些投资者如何判断？当前市场更像哪类历史情形？")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.message.text or ""
    try:
        answer = ChatEngine().answer(question)
    except Exception as exc:  # noqa: BLE001
        answer = f"暂时无法生成回答：{exc}"
    await update.message.reply_text(answer)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("缺少 TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
