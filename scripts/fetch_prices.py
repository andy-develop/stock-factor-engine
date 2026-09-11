#!/usr/bin/env python3
"""增量拉取全 A 股日线前复权收盘价，输出 data/prices.json
增量策略: 读取已有 prices.json，每只股票只拉取从最后交易日到今天的数据
用法: python3 scripts/fetch_prices.py [--limit N] [--workers N]
"""
import json, os, sys, time, urllib.request, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
STOCKS_FILE = os.path.join(DATA_DIR, "stocks.json")
PRICES_FILE = os.path.join(DATA_DIR, "prices.json")

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
KLINE_URL = ("http://push2his.eastmoney.com/api/qt/stock/kline/get?"
             "secid={secid}&fields1=f1,f2,f3,f4,f5,f6&"
             "fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&"
             "klt=101&fqt=1&end=20500101&lmt={lmt}")

def secid_of(code):
    """沪市 6xx -> 1.code, 深市 0xx/3xx -> 0.code, 北交所 8xx/4xx -> 0.code"""
    if code.startswith(("6", "9")):
        return f"1.{code}"
    return f"0.{code}"

def fetch_klines(code, lmt=120):
    """拉取最近 lmt 个交易日K线，返回 [(date, close), ...]"""
    url = KLINE_URL.format(secid=secid_of(code), lmt=lmt)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8"))
    klines = d.get("data", {}).get("klines", []) or []
    result = []
    for line in klines:
        parts = line.split(",")
        if len(parts) >= 3:
            result.append((parts[0], float(parts[2])))  # date, close
    return result

def update_one(code, existing, max_lookback=120):
    """更新单只股票，返回 (code, new_data_or_None)"""
    old = existing.get(code, {"dates": [], "closes": []})
    last_date = old["dates"][-1] if old["dates"] else None
    try:
        klines = fetch_klines(code, lmt=max_lookback)
        if not klines:
            return code, None
        if last_date:
            # 只取比 last_date 新的数据
            new = [(d, c) for d, c in klines if d > last_date]
            if not new:
                return code, None  # 无新数据
            dates = old["dates"] + [d for d, _ in new]
            closes = old["closes"] + [c for _, c in new]
        else:
            dates = [d for d, _ in klines]
            closes = [c for _, c in klines]
        return code, {"dates": dates, "closes": closes}
    except Exception as e:
        return code, None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只处理前N只（调试用）")
    parser.add_argument("--workers", type=int, default=8, help="并发数")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STOCKS_FILE, encoding="utf-8") as f:
        stocks = json.load(f)
    if args.limit:
        stocks = stocks[:args.limit]
    print(f"待更新股票: {len(stocks)} 只")

    # 读取已有价格
    existing = {}
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"已有价格数据: {len(existing)} 只")

    updated = 0
    failed = 0
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(update_one, code, existing): code for code, _ in stocks}
        for i, fut in enumerate(as_completed(futures), 1):
            code, data = fut.result()
            if data:
                results[code] = data
                updated += 1
            else:
                # 保留原有数据
                if code in existing:
                    results[code] = existing[code]
                else:
                    failed += 1
            if i % 500 == 0:
                print(f"  进度 {i}/{len(stocks)}, 新增/更新 {updated}, 失败 {failed}")

    # 写回（合并所有股票）
    for code in existing:
        if code not in results:
            results[code] = existing[code]

    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    print(f"完成: 总计 {len(results)} 只有价格数据, 本次更新 {updated} 只, 失败 {failed} 只")

if __name__ == "__main__":
    main()
