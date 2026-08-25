#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地力スクリーナー(value_finder)のバックテスト。

2026-08-09に「◎ = value_finder の地力1位をそのまま採用」へ運用を変えたので、
地力1位の成績が予想そのものの成績になった。重み・シグナルを触ったら必ずこれを通す。

使い方:
  python3 tools/backtest_value.py            # 地力1〜3位の勝率/複勝率/回収率
  python3 tools/backtest_value.py --detail   # レース別
"""
import json, glob, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_finder import score_horse, to_f


def load():
    base = os.path.dirname(os.path.abspath(__file__))
    rj = json.load(open(os.path.join(base, "..", "races.json"), encoding="utf-8"))
    rs = rj["races"] if isinstance(rj, dict) else rj
    # ⚠ (日付,競馬場)だけでは同日同開催の複数レースを区別できない。raceNoまで含める。
    res = {(r["date"], r["track"], r["raceNo"]): r for r in rs if "result" in r}
    out = []
    for p in sorted(glob.glob(os.path.join(base, "racecards", "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        if not isinstance(d, dict) or not d.get("horses"): continue
        key = (d.get("date"), d.get("track"), d.get("raceNo"))
        # 出馬表自身が result を持っていればそれを使う。
        # 私が予想していないレースも検体にできるようにするため(検体数を増やすのが最優先)。
        if d.get("result"):
            out.append((d, {"name": d.get("name", "?"), "result": d["result"]}))
        elif key in res:
            out.append((d, res[key]))
    return dedup(out, lambda c: (c[0].get("date"), c[0].get("track"), c[0].get("raceNo")))


def dedup(cards, keyfn):
    """同一(日付,競馬場,レース番号)の出馬表が複数あっても1件に絞る。

    2026-08-23時点で別セッションが同じレースの出馬表を別ファイル名で作っており
    (例: 2026-08-23-niigata-2sai.json と 2026-08-23-niigata-niigata-2sai.json)、
    重複したまま集計すると同じレースを二重に数えて検体数と回収率が水増しされる。
    result を自前で持っている方(=結果まで記録済み)を優先して残す。
    """
    best = {}
    for c in cards:
        k = keyfn(c)
        if k not in best or (c[0].get("result") if isinstance(c[0], dict) else False):
            if k in best and not (c[0].get("result") if isinstance(c[0], dict) else False):
                continue
            best[k] = c
    return list(best.values())


def rank(d):
    ws = [to_f(h.get("weight")) for h in d["horses"] if to_f(h.get("weight"))]
    d["_avg_weight"] = sum(ws) / len(ws) if ws else None
    d["_bias"] = d.get("bias")
    return sorted(((score_horse(h, d)[0], h["num"], h["name"]) for h in d["horses"]),
                  key=lambda x: -x[0])


def run(detail=False):
    cards = load()
    n = len(cards)
    stats = {k: {"win": 0, "itm": 0, "tb": 0, "tr": 0, "fb": 0, "fr": 0} for k in (1, 2, 3)}
    rows = []
    for d, r in cards:
        res = r["result"]; top3 = [res["first"], res["second"], res["third"]]
        fk = dict(zip(top3, res.get("fukushoPay") or [0, 0, 0]))
        sc = rank(d)
        for k in (1, 2, 3):
            if len(sc) < k: continue
            num = sc[k - 1][1]; s = stats[k]
            s["tb"] += 100; s["fb"] += 100
            if num == res["first"]: s["win"] += 1; s["tr"] += res.get("tanshoPay", 0)
            if num in top3: s["itm"] += 1; s["fr"] += fk.get(num, 0)
        rows.append((r["name"], sc[0], top3, sc[0][1] in top3))
    print(f"■ 地力スクリーナー バックテスト（{n}鞍）")
    print(f"{'地力順位':<8}{'勝率':>7}{'複勝率':>8}{'単回収':>9}{'複回収':>9}")
    print("-" * 42)
    for k in (1, 2, 3):
        s = stats[k]
        print(f"{k}位{'':<6}{s['win']/n*100:>6.0f}%{s['itm']/n*100:>7.0f}%"
              f"{s['tr']/s['tb']*100:>8.0f}%{s['fr']/s['fb']*100:>8.0f}%")
    if detail:
        print()
        for name, top, top3, hit in rows:
            print(f"  {name[:13]:<14} 地力1位={top[2][:12]:<13} {top[0]:>6.1f}  "
                  f"着順{top3}  {'★複勝圏' if hit else ''}")
    return stats, n


if __name__ == "__main__":
    run(detail="--detail" in sys.argv)
