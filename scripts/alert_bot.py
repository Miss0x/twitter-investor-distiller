"""#5 预警系统 — Phase 4

持仓股异常表态 → Telegram Bot 推送。
需要配置 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 环境变量。
未配置时跳过推送，仅输出日志。

用法：python scripts/alert_bot.py
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ANOMALY_DIR = Path("data/anomaly")
PORTFOLIO_PATH = Path("data/my_portfolio.csv")


def load_portfolio() -> set[str]:
    """加载持仓股票列表。CSV 格式: ticker,cost,shares"""
    if not PORTFOLIO_PATH.exists():
        print(f"⚠️ 无持仓文件: {PORTFOLIO_PATH}")
        print("  创建 data/my_portfolio.csv，格式: ticker,cost,shares")
        return set()
    tickers = set()
    for line in PORTFOLIO_PATH.read_text(encoding="utf-8").strip().split("\n")[1:]:  # skip header
        if line.strip():
            tickers.add(line.split(",")[0].strip().upper())
    return tickers


def send_telegram(message: str) -> bool:
    """从 data/telegram_config.json 读取配置并发送消息。"""
    config_path = Path("data/telegram_config.json")
    if not config_path.exists():
        print(f"  [dry-run] 请先在网页端配置 Telegram → {message[:50]}")
        return False
    config = json.loads(config_path.read_text(encoding="utf-8"))
    token = config.get("bot_token", "")
    chat_id = config.get("chat_id", "")
    if not token or not chat_id:
        print(f"  [dry-run] {message[:50]}")
        return False
    import urllib.request
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)
    return True


def main():
    portfolio = load_portfolio()
    if not portfolio:
        return
    print(f"持仓: {sorted(portfolio)}")

    for fp in sorted(ANOMALY_DIR.glob("*_anomaly.json")):
        username = fp.stem.replace("_anomaly", "")
        data = json.loads(fp.read_text(encoding="utf-8"))

        # 取最近 3 个异常窗口
        recent = [r for r in data if r["anomaly"]][-3:]
        if not recent:
            continue

        # 检查是否涉及持仓股
        for r in recent:
            # 简单检测：异常窗口里的文本是否含持仓 ticker
            topic_hit = any(t in " ".join(r["topics"]) for t in portfolio)
            stance_hit = any(t in " ".join(r["stances"]) for t in portfolio)

            if topic_hit or stance_hit:
                msg = (
                    f"⚠️ <b>{username}</b> 行为异常\n"
                    f"  时间: {r['window_start']}~{r['window_end']}\n"
                    f"  KL散度: {r['kl_avg']:.2f}\n"
                    f"  topics: {', '.join(r['topics'][:3])}\n"
                    f"  stances: {', '.join(r['stances'][:3])}"
                )
                sent = send_telegram(msg)
                if sent:
                    print(f"  ✅ 已推送")


if __name__ == "__main__":
    main()
