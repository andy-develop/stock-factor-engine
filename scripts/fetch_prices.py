#!/usr/bin/env python3
"""增量拉取全 A 股日线前复权收盘价，输出 data/prices.json
增量策略: 读取已有 prices.json，每只股票只拉取从最后交易日到今天的数据
用法: python3 scripts/fetch_prices.py [--limit N] [--workers N]
"""
import json, os, sys, time, urllib.request, argparse, random
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
STOCKS_FILE = os.path.join(DATA_DIR, "stocks.json")
PRICES_FILE = os.path.join(DATA_DIR, "prices.json")

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

NODES = [
    "https://push2his.eastmoney.com",
    "https://1.push2his.eastmoney.com",
    "https://2.push2his.eastmoney.com",
    "http://push2his.eastmoney.com",
]

def secid_of(code):
    """沪市 6xx/9xx -> 1.code, 深市/北交所 0xx/2xx/3xx/4xx/8xx -> 0.code"""
    if code.startswith(("6", "9")):
        return f"1.{code}"
    return f"0.{code}"

def fetch_klines(code, lmt=120):
    """拉取最近 lmt 个交易日K线，返回 [(date, close), ...]，失败抛异常"""
    last_err = None
    for node in NODES:
        url = (f"{node}/api/qt/stock/kline/get?"
               f"secid={secid_of(code)}&fields1=f1,f2,f3,f4,f5,f6&"
               f"fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&"
               f"klt=101&fqt=1&end=20500101&lmt={lmt}")
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8"))
            klines = d.get("data", {}).get("klines", []) or []
            if not klines:
                return []
            result = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 3:
                    try:
                        result.append((parts[0], float(parts[2])))
                    except (ValueError, IndexError):
                        continue
            return result
        except Exception as e:
            last_err = e
            time.sleep(0.3 + random.random() * 0.3)
    raise last_err if last_err else Exception("all nodes failed")

def update_one(code, existing, max_lookback=120):
    """更新单只股票，最多重试5次，返回 (code, new_data_or_None)"""
    old = existing.get(code, {"dates": [], "closes": []})
    last_date = old["dates"][-1] if old["dates"] else None

    for attempt in range(5):
        try:
            klines = fetch_klines(code, lmt=max_lookback)
            if not klines:
                return code, None  # 无数据（退市/停牌）
            if last_date:
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
            if attempt < 4:
                time.sleep(1 + attempt * 1.5 + random.random())
            else:
                return code, None  # 重试耗尽

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只处理前N只（调试用）")
    parser.add_argument("--workers", type=int, default=6, help="并发数（默认6，避免限流）")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STOCKS_FILE, encoding="utf-8") as f:
        stocks = json.load(f)
    if args.limit:
        stocks = stocks[:args.limit]
    print(f"待更新股票: {len(stocks)} 只, 并发: {args.workers}")

    # 读取已有价格
    existing = {}
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"已有价格数据: {len(existing)} 只")

    updated = 0
    failed = 0
    no_data = 0
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(update_one, code, existing): code for code, _ in stocks}
        for i, fut in enumerate(as_completed(futures), 1):
            code, data = fut.result()
            if data:
                results[code] = data
                updated += 1
            elif code in existing:
                results[code] = existing[code]
                no_data += 1
            else:
                failed += 1
            if i % 500 == 0:
                print(f"  进度 {i}/{len(stocks)}, 新增/更新 {updated}, 无新数据 {no_data}, 失败 {failed}")

    # 合并所有已有数据
    for code in existing:
        if code not in results:
            results[code] = existing[code]

    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    print(f"完成: 总计 {len(results)} 只有价格数据, 本次更新 {updated} 只, 无新数据 {no_data}, 失败 {failed} 只")
    if failed > len(stocks) * 0.3:
        print(f"警告: 失败率较高({failed}/{len(stocks)})，可能被API限流")

if __name__ == "__main__":
    main()
