"""拉取所有 ticker 的 yfinance sector/industry，存到 data/sector_map.json。"""
import json, time, re
from pathlib import Path
from collections import defaultdict

try:
    import yfinance as yf
except ImportError:
    print("请先: pip install yfinance")
    exit(1)

TICKER_PAT = re.compile(r'^[A-Z]{1,5}$')

tickers = set()
for fp in Path('data/pipeline').glob('*_analyzed_cleaned.json'):
    for r in json.loads(fp.read_text(encoding='utf-8')):
        for s in r.get('stock_details', []):
            t = s.get('ticker', '').strip().upper()
            if t and TICKER_PAT.match(t):
                tickers.add(t)

print(f'美股 ticker: {len(tickers)} 只')

sector_map = {}
errors = []
for i, t in enumerate(sorted(tickers)):
    try:
        info = yf.Ticker(t).info
        sector_map[t] = {
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
        }
        print(f'  [{i+1}/{len(tickers)}] {t}: {info.get("sector","?")} / {info.get("industry","?")}')
    except Exception as e:
        errors.append(t)
        sector_map[t] = {'sector': '', 'industry': ''}
        print(f'  [{i+1}/{len(tickers)}] {t}: ❌ {e}')
    time.sleep(0.8)

# 统计
sector_groups = defaultdict(list)
industry_groups = defaultdict(list)
for t, v in sector_map.items():
    if v['sector']:
        sector_groups[v['sector']].append(t)
    if v['industry']:
        industry_groups[v['industry']].append(t)

print(f'\n成功: {len(sector_map)-len(errors)}, 失败: {len(errors)}')

print(f'\n=== Sector ({len(sector_groups)} 类) ===')
for sec, stocks in sorted(sector_groups.items(), key=lambda x: -len(x[1])):
    print(f'  {sec}: {len(stocks)}只 [{", ".join(stocks[:8])}]')

print(f'\n=== Industry ({len(industry_groups)} 类) ===')
for ind, stocks in sorted(industry_groups.items(), key=lambda x: -len(x[1])):
    print(f'  {ind}: {len(stocks)}只 [{", ".join(stocks[:8])}]')

out = Path('data/sector_map.json')
out.write_text(json.dumps(sector_map, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\n✅ data/sector_map.json')
