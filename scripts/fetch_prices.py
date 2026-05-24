"""Polygon 股价批量拉取 —— 单只 13s 间隔，渐进保存。"""
import json, time, sys, urllib.request, urllib.error, yaml
from datetime import date
from pathlib import Path

with open(Path(__file__).parent.parent / "config" / "pipeline.yaml", encoding="utf-8") as _f:
    _CFG = yaml.safe_load(_f) or {}
POLYGON_KEY = _CFG.get("api", {}).get("polygon_key", "")
OUTPUT = Path(__file__).parent.parent / "data" / "prices.json"
FROM_DATE = _CFG.get("api", {}).get("polygon_from_date", "2015-01-01")


def fetch_ticker(ticker: str) -> dict | None:
    to_date = date.today().strftime("%Y-%m-%d")
    url = (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
           f"{FROM_DATE}/{to_date}?apiKey={POLYGON_KEY}&limit=5000")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            if resp.get("resultsCount", 0) > 0:
                return resp
            return None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 20 * (attempt + 1)
                print(f"429(重试{attempt+1}/{3},等{wait}s)...", end=" ", flush=True)
                time.sleep(wait)
                continue
            return None
        except Exception as e:
            return None
    return None


def main():
    # 加载已有数据
    prices = {}
    if OUTPUT.exists():
        prices = json.loads(OUTPUT.read_text(encoding="utf-8"))
        print(f"续: 已有 {len(prices)} 只")

    # 从所有分析文件中收集股票
    import re
    from collections import Counter
    stocks = Counter()
    for fp in Path("data/pipeline").glob("*_analyzed.json"):
        if "_cleaned" in fp.name:
            continue
        for r in json.loads(fp.read_text(encoding="utf-8")):
            for s in r.get("mentioned_stocks", []):
                s = s.strip().lstrip("$")
                if re.match(r"^[A-Z]{1,5}$", s) and s not in ('AI','ETF','ATH','USD','IPO','CEO','CFO','ALL','DSP','OC','BOM'):
                    stocks[s] += 1
    tickers = [s for s, _ in stocks.most_common()]

    print(f"拉取 {len(tickers)} 只股票...")
    total = len(tickers)
    new_count = 0
    for i, ticker in enumerate(tickers):
        if ticker in prices:
            continue
        print(f"  [{i+1}/{total}] {ticker} (提到 {stocks[ticker]} 次)...", end=" ", flush=True)
        data = fetch_ticker(ticker)
        if data:
            prices[ticker] = data
            new_count += 1
            print("OK")
        else:
            prices[ticker] = None
            print("EMPTY")
        # 逐个保存
        valid = {k: v for k, v in prices.items() if v is not None}
        OUTPUT.write_text(json.dumps(valid, ensure_ascii=False), encoding="utf-8")
        time.sleep(15)  # 5/min = 每 12 秒一个，15s 留足余量

    # 最终保存
    OUTPUT.write_text(json.dumps({k: v for k, v in prices.items() if v is not None}, ensure_ascii=False), encoding="utf-8")
    valid = sum(1 for v in prices.values() if v is not None)
    print(f"\n完成: {valid}/{len(prices)} 只有数据 → {OUTPUT}")


if __name__ == "__main__":
    main()
