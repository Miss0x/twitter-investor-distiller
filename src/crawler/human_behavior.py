"""阶段 3：真人行为控制模块。"""
from __future__ import annotations

import random
from dataclasses import dataclass

from playwright.sync_api import Page


@dataclass(slots=True)
class HumanBehaviorProfile:
    """真人行为参数配置。"""

    min_pause_ms: int = 700
    max_pause_ms: int = 1800
    min_scroll_px: int = 600
    max_scroll_px: int = 1400
    backtrack_probability: float = 0.2
    min_backtrack_px: int = 120
    max_backtrack_px: int = 420
    expand_probability: float = 0.15


class HumanBehaviorController:
    """对 Playwright Page 执行轻量真人化动作。"""

    def __init__(self, profile: HumanBehaviorProfile | None = None, *, seed: int | None = None) -> None:
        self.profile = profile or HumanBehaviorProfile()
        self._random = random.Random(seed)

    def random_pause(self, page: Page, stage: str = "default") -> None:
        multiplier = 1.0
        if stage == "navigation":
            multiplier = 1.4
        elif stage == "scan":
            multiplier = 0.8
        duration = int(self._random.randint(self.profile.min_pause_ms, self.profile.max_pause_ms) * multiplier)
        page.wait_for_timeout(duration)

    def stabilize_after_navigation(self, page: Page) -> None:
        self.random_pause(page, stage="navigation")
        self._maybe_move_mouse(page)

    def scroll_timeline(self, page: Page) -> int:
        distance = self._random.randint(self.profile.min_scroll_px, self.profile.max_scroll_px)
        page.mouse.wheel(0, distance)
        self.random_pause(page, stage="scan")
        return distance

    def micro_backtrack(self, page: Page) -> int:
        if self._random.random() > self.profile.backtrack_probability:
            return 0
        distance = self._random.randint(self.profile.min_backtrack_px, self.profile.max_backtrack_px)
        page.mouse.wheel(0, -distance)
        self.random_pause(page, stage="scan")
        return distance

    def maybe_expand_text(self, page: Page) -> bool:
        if self._random.random() > self.profile.expand_probability:
            return False
        selectors = [
            "div[data-testid='tweetText'] span",
            "div[role='button'][data-testid='caret']",
            "div[role='button'] span:has-text('Show more')",
            "div[role='button'] span:has-text('显示更多')",
        ]
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if locator.count() > 0:
                    locator.click(timeout=1000)
                    self.random_pause(page, stage="scan")
                    return True
            except Exception:
                continue
        return False

    def _maybe_move_mouse(self, page: Page) -> None:
        width = page.viewport_size["width"] if page.viewport_size else 1365
        height = page.viewport_size["height"] if page.viewport_size else 900
        x = self._random.randint(80, max(100, width - 80))
        y = self._random.randint(80, max(100, min(height - 80, 400)))
        steps = self._random.randint(8, 20)
        page.mouse.move(x, y, steps=steps)
