"""Telegram Bot 接口模块。

基于 python-telegram-bot 库实现的 Telegram 聊天机器人，支持:
    - /start: 欢迎消息
    - /help: 使用帮助
    - 文本消息: 调用 ChatEngine 进行 AI 问答

启动方式:
    python -m src.interfaces.telegram_bot

环境变量依赖:
    TELEGRAM_BOT_TOKEN: Telegram Bot API Token（通过 @BotFather 获取）

用法:
    from src.interfaces.telegram_bot import main
    main()
"""
from __future__ import annotations

import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from src.ai.chat_engine import ChatEngine
from src.utils.env import load_project_env

# 加载环境变量（包含 TELEGRAM_BOT_TOKEN）
load_project_env()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /start 命令：发送欢迎消息。

    Args:
        update: Telegram 更新对象（包含消息和用户信息）
        context: 回调上下文（Bot 实例等）
    """
    await update.message.reply_text("欢迎使用 Twitter 用户蒸馏 AI 助手。直接发送问题即可开始。")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理 /help 命令：发送使用帮助。

    Args:
        update: Telegram 更新对象
        context: 回调上下文
    """
    await update.message.reply_text(
        "你可以问：某个标的怎么看？某个叙事这些投资者如何判断？当前市场更像哪类历史情形？"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理用户文本消息：调用 ChatEngine 生成 AI 回复。

    业务逻辑:
        1. 提取用户问题文本
        2. 创建 ChatEngine 实例调用 answer() 方法
        3. 异常时返回友好提示（而非直接抛出崩溃）

    Args:
        update: Telegram 更新对象
        context: 回调上下文
    """
    question = update.message.text or ""  # 提取消息文本（可能为空）
    try:
        # 调用 ChatEngine 获取 AI 回答
        answer = ChatEngine().answer(question)
    except Exception as exc:
        # 捕获所有异常，避免 Bot 崩溃
        answer = f"暂时无法生成回答：{exc}"
    await update.message.reply_text(answer)


def main() -> None:
    """Bot 主入口：构建 Application、注册 Handler、启动轮询。

    流程:
        1. 检查 TELEGRAM_BOT_TOKEN 环境变量
        2. 创建 Application 实例
        3. 注册命令和消息处理器
        4. 启动长轮询（阻塞运行）

    Raises:
        RuntimeError: 缺少 TELEGRAM_BOT_TOKEN 时抛出
    """
    # 从环境变量读取 Bot Token
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("缺少 TELEGRAM_BOT_TOKEN（请在 .env 文件或系统环境变量中设置）")

    # 构建 Telegram Application 实例
    app = Application.builder().token(token).build()

    # 注册命令处理器
    app.add_handler(CommandHandler("start", start))       # /start 命令
    app.add_handler(CommandHandler("help", help_command))  # /help 命令

    # 注册文本消息处理器（非命令文本消息）
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 启动长轮询，持续监听用户消息
    app.run_polling()


if __name__ == "__main__":
    main()
