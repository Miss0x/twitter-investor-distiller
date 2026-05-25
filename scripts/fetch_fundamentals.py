"""#11 基本面快照 — Phase 1 辅助模块

从 analyzed_cleaned 提取所有已验证 ticker，调 westock-data 拉取 PE/ROE/营收增速/负债率。
数据源：腾讯自选股（westock-data skill），免费无限额。

用法：python scripts/fetch_fundamentals.py
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

WESTOCK_JS = Path.home() / ".workbuddy/plugins/marketplaces/cb_teams_marketplace/plugins/finance-data/skills/westock-data/scripts/index.js"
CACHE_PATH = Path("data/fundamental_cache.json")
PIPELINE_DIR = Path("data/pipeline")


def collect_tickers() -> list[str]:
    seen = set()
    for fp in sorted(PIPELINE_DIR.glob("*_analyzed_cleaned.json")):
        for r in json.loads(fp.read_text(encoding="utf-8")):
            for s in r.get("stock_details", []):
                t = s.get("ticker", "").strip().upper()
                if t and t not in ("3677",):
                    seen.add(t)
    # 只保留看起来像美股 ticker 的（1-5 大写字母）
    import re
    valid = [t for t in seen if re.match(r"^[A-Z]{1,5}(\.[A-Z])?$", t)]
    return sorted(valid)


def run_westock(*args: str) -> str:
    try:
        r = subprocess.run(["node", str(WESTOCK_JS), *args], capture_output=True, text=True, timeout=15, cwd=WESTOCK_JS.parent)
        return r.stdout
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as e:
        return f"ERROR: {e}"


def parse_quote(stdout: str) -> dict:
    """从 quote Markdown 表格提取 PE/PB/市值。"""
    res: dict = {}
    lines = stdout.split("\n")
    headers: list[str] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        if "---" in line:
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if not headers:
            headers = parts
            continue
        if len(parts) == len(headers):
            for i, h in enumerate(headers):
                v = parts[i]
                if h == "pe_ratio":
                    try: res["pe_ratio"] = float(v.replace(",", ""))
                    except: pass
                elif h == "pb_ratio":
                    try: res["pb_ratio"] = float(v.replace(",", ""))
                    except: pass
                elif h == "total_market_cap":
                    try: res["market_cap"] = float(v.replace(",", ""))
                    except: pass
                elif h == "name":
                    res["name"] = v
            break
    return res


def parse_finance_table(stdout: str, table_name: str) -> list[dict]:
    lines = stdout.split("\n")
    in_table = False
    headers: list[str] = []
    rows: list[dict] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("**" + table_name + "**"):
            in_table = True
            continue
        if in_table and s.startswith("**"):
            break
        if in_table:
            if not headers:
                headers = [h.strip() for h in s.split("|")[1:-1]]
            elif "---" in s:
                continue
            elif s.startswith("|"):
                vals = [v.strip() for v in s.split("|")[1:-1]]
                if len(vals) == len(headers):
                    rows.append(dict(zip(headers, vals)))
    return rows


def fetch_one(ticker: str) -> dict:
    print(f"  {ticker}...", end=" ", flush=True)
    res: dict = {"ticker": ticker, "fetched_at": time.strftime("%Y-%m-%d")}

    try:
        quote_out = run_westock("quote", f"us{ticker}")
        res.update(parse_quote(quote_out))

        fin_out = run_westock("finance", f"us{ticker}", "--num", "4")
        inc = parse_finance_table(fin_out, "income")
        bal = parse_finance_table(fin_out, "balance")
        cf = parse_finance_table(fin_out, "cashflow")

        if bal:
            lb = bal[-1]
            try: res["roe"] = float(lb.get("ROE", 0))
            except: pass
            try:
                liab = float(lb.get("TotalLiabilities", 0))
                assets = float(lb.get("TotalAssets", 0))
                if assets > 0:
                    res["debt_ratio"] = round(liab / assets, 4)
            except: pass

        if len(inc) >= 2:
            try:
                s0 = float(inc[-1].get("Sales_Q", 0))
                s1 = float(inc[-2].get("Sales_Q", 0))
                if s1 > 0:
                    res["revenue_growth_yoy"] = round((s0 - s1) / s1, 4)
            except: pass

        if cf:
            try: res["free_cash_flow_q"] = float(cf[-1].get("FreeCF_Q", 0))
            except: pass

    except Exception as e:
        res["_error"] = str(e)[:200]
        print(f"❌ {e}")
        return res

    ok = "pe_ratio" in res or "roe" in res
    print("✅" if ok else "⚠️")
    return res


def main():
    cache: dict = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    tickers = collect_tickers()
    new = [t for t in tickers if t not in cache]
    print(f"有效 ticker: {len(tickers)} 只, 需拉取: {len(new)} 只")

    if not new:
        print("全部已缓存。")
        return

    cnt = 0
    for ticker in new:
        try:
            cache[ticker] = fetch_one(ticker)
            cnt += 1
            if cnt % 10 == 0:
                CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            cache[ticker] = {"ticker": ticker, "_error": str(e)[:200]}
        time.sleep(0.2)

    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    has_pe = sum(1 for v in cache.values() if "pe_ratio" in v)
    has_roe = sum(1 for v in cache.values() if "roe" in v)
    print(f"\n完成: {cnt} 只。PE覆盖 {has_pe}, ROE覆盖 {has_roe}")


if __name__ == "__main__":
    main()
