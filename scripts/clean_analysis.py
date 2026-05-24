"""分析结果清洗校准 —— 股票去重、分类、验证。"""
import csv, json, re, sys
from collections import defaultdict
from pathlib import Path

PRICES_PATH = Path("data/prices.json")
ALIAS_PATH = Path("data/stock_alias.csv")

# 已知分类（手动 + 自动推断）
KNOWN_ETFS = {"SOXS", "SOXL", "TQQQ", "SQQQ", "SPY", "QQQ", "UVXY", "XLE", "XLF", "IWM", 
              "DIA", "VOO", "VTI", "ARKK", "AMDL", "SOXX", "SMH", "POWR", "JNK"}
KNOWN_CRYPTO = {"BTC", "ETH", "XRP", "SOL", "DOGE", "ADA", "AVAX", "DOT", "MATIC"}
KNOWN_INDEX = {"SPX", "NDX", "DJI", "RUT", "VIX"}
KNOWN_BONDS = {"TLT", "IEF", "SHY", "BND"}


def load_alias() -> dict[str, str]:
    alias = {}
    if ALIAS_PATH.exists():
        with open(ALIAS_PATH, encoding="utf-8") as f:
            for row in csv.reader(f):
                if row and not row[0].startswith("#") and len(row) >= 2:
                    a, t = row[0].strip().lstrip("$"), row[1].strip().lstrip("$")
                    if a and t:
                        alias[a.lower()] = t.upper()
                        alias[a.upper()] = t.upper()
                        alias[a] = t.upper()
    return alias


def load_known_tickers() -> set[str]:
    """从已有股价数据和常用列表构建已知 ticker 集合。"""
    known = set()
    if PRICES_PATH.exists():
        prices = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
        known.update(prices.keys())
    known.update(KNOWN_ETFS | KNOWN_CRYPTO | KNOWN_INDEX | KNOWN_BONDS)
    return known


def classify(ticker: str) -> str:
    """推断类型。"""
    upper = ticker.upper()
    if upper in KNOWN_CRYPTO:
        return "crypto"
    if upper in KNOWN_ETFS:
        return "etf"
    if upper in KNOWN_INDEX:
        return "index"
    if upper in KNOWN_BONDS:
        return "bond"
    # 以 -USD 结尾的可能是加密
    if ticker.endswith("-USD"):
        return "crypto"
    return "stock"


def clean_stocks(raw_list: list[str], alias: dict, known: set) -> list[dict]:
    """清洗单条推文的股票列表。返回 [{ticker, type, original}]。"""
    seen = set()
    cleaned = []

    for raw in raw_list:
        s = str(raw).strip().lstrip("$")
        if not s or len(s) < 1:
            continue

        lowered = s.lower()
        # 1. 查别名表
        if lowered in alias:
            s = alias[lowered]
        elif s.upper() in alias:
            s = alias[s.upper()]

        # 2. 标准化（去掉常见后缀）
        s = re.sub(r"(股票|\.US|\.ETF)$", "", s, flags=re.IGNORECASE)

        # 3. 去重
        key = s.upper()
        if key in seen:
            continue
        seen.add(key)

        # 4. 验证 + 分类
        is_known = key in known or bool(len(key) <= 5 and re.match(r"^[A-Z0-9.-]+$", key))
        # 标准美股格式直接视为 stock
        is_standard = bool(re.match(r"^[A-Z]{1,5}$", key))

        if is_standard:
            ticker_type = classify(key)
            cleaned.append({
                "ticker": key,
                "type": ticker_type,
                "original": raw if raw != key else None,
                "verified": is_known
            })
            continue

        if not is_known:
            cleaned.append({"ticker": key, "type": "unknown", "original": raw, "verified": False})
            continue

        cleaned.append({
            "ticker": key,
            "type": classify(key),
            "original": raw if raw != key else None,
            "verified": True
        })

    return cleaned


def clean_crypto(raw_list: list[str], alias: dict) -> list[str]:
    """清洗加密货币列表。"""
    names = []
    for raw in raw_list:
        s = str(raw).strip()
        lowered = s.lower()
        if lowered in alias:
            s = alias[lowered]
        # 标准化
        s = re.sub(r"(比特币|Bitcoin)", "BTC", s, flags=re.IGNORECASE)
        s = re.sub(r"(以太坊|Ethereum)", "ETH", s, flags=re.IGNORECASE)
        s = s.strip().upper()
        if s and s not in names and len(s) <= 10:
            names.append(s)
    return names


def main():
    alias = load_alias()
    known = load_known_tickers()
    print(f"别名: {len(alias)} 条")
    print(f"已知 ticker: {len(known)} 个")

    files = list(Path("data/pipeline").glob("*_analyzed.json"))
    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8"))
        total = len(data)
        stats = defaultdict(int)
        cleaned_data = []

        for r in data:
            # 清洗 stocks
            raw_stocks = r.get("mentioned_stocks", [])
            stock_details = clean_stocks(raw_stocks, alias, known)
            r["stock_details"] = stock_details

            # 更新提及数统计
            for sd in stock_details:
                stats[f"{sd['type']}"] += 1
                if not sd["verified"]:
                    stats["unverified"] += 1

            # 清洗 crypto
            raw_crypto = r.get("mentioned_crypto", [])
            r["crypto_details"] = clean_crypto(raw_crypto, alias)

            cleaned_data.append(r)

        # 写入清洗版
        out_path = fp.parent / f"{fp.stem}_cleaned.json"
        out_path.write_text(json.dumps(cleaned_data, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n{fp.name}: {total} 条")
        print(f"  股票: {stats.get('stock',0)}, ETF: {stats.get('etf',0)}, 加密: {stats.get('crypto',0)}")
        print(f"  指数: {stats.get('index',0)}, 债券: {stats.get('bond',0)}, 未识别: {stats.get('unknown',0)}")
        print(f"  未验证: {stats.get('unverified',0)}")
        print(f"  → {out_path.name}")

    print("\n清洗完成！")


if __name__ == "__main__":
    main()
