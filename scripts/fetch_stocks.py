#!/usr/bin/env python3
"""拉取全 A 股股票列表，输出 data/stocks.json
用法: python3 scripts/fetch_stocks.py
"""
import json, os, sys, time, urllib.request

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUT = os.path.join(DATA_DIR, "stocks.json")

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def fetch_page(pn, pz=100):
    url = (f"http://82.push2.eastmoney.com/api/qt/clist/get?"
           f"pn={pn}&pz={pz}&po=1&np=1&fltt=2&invt=2&fid=f3&"
           f"fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&"
           f"fields=f12,f14")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    # 先探总数
    first = fetch_page(1, 1)
    total = first.get("data", {}).get("total", 0)
    print(f"全 A 股总数: {total}")
    pages = (total + 99) // 100
    stocks = []
    for pn in range(1, pages + 1):
        for attempt in range(3):
            try:
                d = fetch_page(pn, 100)
                items = d.get("data", {}).get("diff", []) or []
                for it in items:
                    code = it.get("f12", "")
                    name = it.get("f14", "")
                    if code and name:
                        stocks.append([code, name])
                print(f"  第 {pn}/{pages} 页，累计 {len(stocks)} 只")
                break
            except Exception as e:
                print(f"  第 {pn} 页失败({attempt+1}/3): {e}")
                time.sleep(2)
        time.sleep(0.15)
    # 去重
    seen = set()
    uniq = []
    for c, n in stocks:
        if c not in seen:
            seen.add(c)
            uniq.append([c, n])
    uniq.sort(key=lambda x: x[0])
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(uniq, f, ensure_ascii=False)
    print(f"完成: {len(uniq)} 只 -> {OUT}")

if __name__ == "__main__":
    main()
