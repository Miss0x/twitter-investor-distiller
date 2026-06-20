"""行情拉取任务 — Polygon.io API 封装。

从 task_executor.py 抽出。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from src.pipeline.task_executor import POLYGON_KEY, PRICES_PATH, CRYPTO_PRICES_PATH, _PIPELINE_CFG


def _fetch_price(ticker: str) -> dict:
    return _fetch_polygon(ticker, PRICES_PATH)


def _fetch_crypto(ticker: str) -> dict:
    return _fetch_polygon(f"X:{ticker}USD", CRYPTO_PRICES_PATH)


def _fetch_polygon(ticker: str, store_path: Path) -> dict:
    from_date = _PIPELINE_CFG.get("api", {}).get("polygon_from_date", "2015-01-01")
    to_date = date.today().strftime("%Y-%m-%d")
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
           f"{from_date}/{to_date}?apiKey={POLYGON_KEY}&limit=5000")
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if resp.get("resultsCount", 0) > 0:
                prices = {}
                if store_path.exists():
                    prices = json.loads(store_path.read_text(encoding="utf-8"))
                prices[ticker] = resp
                store_path.write_text(json.dumps(prices, ensure_ascii=False), encoding="utf-8")
                return {"ok": True, "bars": resp["resultsCount"]}
            return {"error": "无数据"}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15)
                continue
            return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": str(e)}
    return {"error": "重试失败"}
