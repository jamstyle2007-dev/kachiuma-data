#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大穴ファインダーのバックテスト。

racecards/*.json と races.json の結果(1-3着)を突き合わせ、
「◆狙い(閾値以上)の馬が実際に複勝圏へ来たか」を実測する。
シグナルの重みを変えたら必ずこれを通してから採用する。

使い方:
  python3 tools/backtest_longshot.py            # 現行ロジック
  python3 tools/backtest_longshot.py --detail   # レース別の内訳も出す
"""
import json, glob, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import longshot_finder as lf


def load_races():
    """(日付, 競馬場) -> 結果 のマップ。"""
    rj = json.load(open(os.path.join(os.path.dirname(__file__), "..", "races.json"), encoding="utf-8"))
    rs = rj["races"] if isinstance(rj, dict) else rj
    # ⚠ (日付,競馬場)だけでは同日同開催の複数レースを区別できない。raceNoまで含める。
    return {(r["date"], r["track"], r["raceNo"]): r for r in rs if "result" in r}


def load_cards(results):
    """結果が確定している出馬表だけを返す。"""
    out = []
    base = os.path.join(os.path.dirname(__file__), "racecards", "*.json")
    for p in sorted(glob.glob(base)):
        d = json.load(open(p, encoding="utf-8"))
        if not isinstance(d, dict) or not d.get("horses"): continue
        key = (d.get("date"), d.get("track"), d.get("raceNo"))
        # 出馬表自身の result を優先。予想していないレースも検体に使う。
        if d.get("result"):
            r = {"name": d.get("name", "?"), "result": d["result"]}
        elif key in results:
            r = results[key]
        else:
            continue
        top3 = [r["result"]["first"], r["result"]["second"], r["result"]["third"]]
        out.append((os.path.basename(p), d, r, top3))
    return dedup2(out)


def dedup2(cards):
    """同一レースの出馬表が複数あっても1件に絞る(別セッションが重複ファイルを作るため)。"""
    best = {}
    for c in cards:
        d = c[1]; k = (d.get("date"), d.get("track"), d.get("raceNo"))
        if k not in best or d.get("result"): best[k] = c
    return list(best.values())


def run(threshold=lf.THRESHOLD, detail=False):
    cards = load_cards(load_races())
    tot = hit = pick = pick_hit = 0
    rows = []
    for fn, d, r, top3 in cards:
        ws = [lf.to_f(h.get("weight")) for h in d["horses"] if lf.to_f(h.get("weight"))]
        d["_avg_weight"] = sum(ws) / len(ws) if ws else None
        longs = [h for h in d["horses"] if h.get("popularity") and h["popularity"] >= lf.MIN_POP]
        picked, phit = [], []
        for h in longs:
            s, _ = lf.score(h, d)
            itm = h["num"] in top3
            tot += 1; hit += itm
            if s >= threshold:
                pick += 1; pick_hit += itm
                picked.append((h["num"], h["name"], h["popularity"], s))
                if itm: phit.append(h["name"])
        rows.append((r["name"], len(longs), picked, phit,
                     [n for n in top3 if any(h["num"] == n and h.get("popularity", 0) >= lf.MIN_POP
                                             for h in d["horses"])]))
    print(f"■ 大穴ファインダー バックテスト（{len(cards)}鞍 / 閾値{threshold}点）")
    print(f"  母集団: {lf.MIN_POP}番人気以下 {tot}頭 / うち複勝圏 {hit}頭 = ベース {hit/tot*100:.0f}%")
    if pick:
        print(f"  ◆狙い : {pick}頭 / うち複勝圏 {pick_hit}頭 = {pick_hit/pick*100:.0f}%"
              f"  （ベース比 {pick_hit/pick/(hit/tot):.1f}倍）")
        print(f"  捕捉率 : 穴で複勝圏に来た{hit}頭のうち {pick_hit}頭を事前指名 = {pick_hit/hit*100:.0f}%")
    else:
        print("  ◆狙い : 0頭")
    if detail:
        print()
        for name, n, picked, phit, actual in rows:
            got = "/".join(phit) or "-"
            print(f"  {name[:12]:<13} 穴{n:>2}頭 ◆{len(picked):>2}頭 → 的中 {got:<20} (穴で複勝圏:{actual})")
    return pick, pick_hit, tot, hit


if __name__ == "__main__":
    run(detail="--detail" in sys.argv)
