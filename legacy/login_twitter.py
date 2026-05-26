"""辅助脚本：启动浏览器让用户登录 Twitter/X，并保存 Cookies。"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

COOKIES_PATH = Path("data/cookies.json")


def main() -> None:
    print("即将启动浏览器，请手动登录 Twitter/X。")
    print("登录成功后，关闭浏览器窗口即可自动保存 Cookies。\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://x.com/login")

        print("请在浏览器中完成登录（包括可能的验证码/2FA）。")
        print("登录完成后，关闭浏览器窗口...\n")

        # 等待浏览器关闭
        while len(browser.contexts) > 0 and len(browser.contexts[0].pages) > 0:
            page.wait_for_timeout(1000)

        cookies = context.cookies()
        COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ Cookies 已保存到 {COOKIES_PATH}，共 {len(cookies)} 条")
        browser.close()


if __name__ == "__main__":
    main()
