"""拉取所有美股 ticker 的 SIC 行业分类，存到 data/sic_map.json。"""
import json, urllib.request, time, re
from pathlib import Path
from collections import defaultdict

API_KEY = '3bP0P8HB1jDNmGuHvOzag22pQnPnaZdM'

tickers = set()
for fp in Path('data/pipeline').glob('*_analyzed_cleaned.json'):
    for r in json.loads(fp.read_text(encoding='utf-8')):
        for s in r.get('stock_details', []):
            t = s.get('ticker', '').strip().upper()
            if t and re.match(r'^[A-Z]{1,5}$', t):
                tickers.add(t)

print(f'美股 ticker: {len(tickers)} 只')

sic_map = {}
errors = []
for i, t in enumerate(sorted(tickers)):
    if i > 0 and i % 4 == 0:
        time.sleep(14)
    try:
        url = f'https://api.polygon.io/v3/reference/tickers/{t}?apiKey={API_KEY}'
        d = json.loads(urllib.request.urlopen(url, timeout=10).read())['results']
        sic_map[t] = {'sic': d.get('sic_code'), 'desc': d.get('sic_description'), 'name': d.get('name', '')[:80]}
        print(f'  [{i+1}/{len(tickers)}] {t}: SIC={d.get("sic_code")} {d.get("sic_description", "")[:50]}')
    except Exception as e:
        errors.append(f'{t}: {e}')

sector_groups = defaultdict(list)
for t, v in sic_map.items():
    sector_groups[f'{v["sic"]} - {v["desc"]}'].append(t)

print(f'\n=== SIC 行业分类 ({len(sic_map)}/{len(tickers)} 成功) ===')
for key, stocks in sorted(sector_groups.items(), key=lambda x: -len(x[1])):
    print(f'📌 {key} ({len(stocks)}只): {sorted(stocks)}')

Path('data/sic_map.json').write_text(json.dumps(sic_map, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\n存盘完成')
