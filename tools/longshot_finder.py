#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大穴ファインダー: 人気薄(6番人気以下)から複勝圏に来る馬を炙り出す。

JACK指摘(2026-08-03)「アイビスの2着14人気・3着11人気を的中できるように」への回答。
8レース64頭の穴馬を実測して有効シグナルだけを残した:

  同コース好走(3着内)  複勝圏率 57% (ベース16%の3.7倍)  ← 最強
  前走1着              複勝圏率 44% (2.8倍)
  同コース好走 or 前走1着  46% (3.0倍) / 両方持ち 67% (4.3倍)
  惜敗継続             18% (1.1倍) ← ほぼ無力。value_finderでの重用は穴には効かない

value_finder(地力)は人気馬の序列付け用。こちらは"クラスが下でもコース適性で勝負になる馬"を拾う。
特にアイビスSD(新潟千直)のような特殊コースでは、クラス差よりコース実績が支配的。

使い方: python3 tools/longshot_finder.py tools/racecards/2026-08-02-niigata-ibis.json
"""
import sys, json

MIN_POP = 6          # これ以下の人気は"穴"として扱わない
DIST_TOL = 100       # 同コース判定の距離許容


def to_f(x):
    try: return float(x)
    except (TypeError, ValueError): return None


def same_course(r, race):
    """同競馬場×同馬場×距離±100m = 実質同じコース条件"""
    return (r.get("track") == race["track"]
            and (r.get("surface") or race["surface"]) == race["surface"]
            and r.get("distance") and abs(r["distance"] - race["distance"]) <= DIST_TOL)


def score(h, race):
    rec = [x for x in (h.get("recent3") or []) if x]
    pts, why = 0.0, []

    # 1) 同コース好走(最強シグナル)。着順が良いほど加点
    best = None
    for r in rec:
        if same_course(r, race):
            f = r.get("finish")
            if f and (best is None or f < best): best = f
    if best is not None:
        if best == 1:   pts += 35; why.append(f"同コース1着")
        elif best <= 3: pts += 30; why.append(f"同コース{best}着")
        elif best <= 5: pts += 12; why.append(f"同コース{best}着")
        else:           pts += 8;  why.append(f"同コース経験({best}着)")

    # 2) 前走1着(勢い)
    if rec and rec[0].get("finish") == 1:
        pts += 25; why.append("前走1着")
        m = to_f(rec[0].get("margin"))
        if m is not None and abs(m) >= 0.3:
            pts += 5; why.append("(楽勝)")

    # 3) 馬場状態が一致する実績(アイビスの教訓: 稍重の前哨戦は良馬場本番で無効化)
    cond = race.get("trackCondition")
    if cond:
        for r in rec:
            if same_course(r, race) and r.get("cond") and str(r["cond"])[0] == str(cond)[0] \
               and (r.get("finish") or 99) <= 5:
                pts += 8; why.append("同馬場状態で好走"); break

    # 4) 人気を大きく裏切らせた実績(穴を開けたことがある)
    for r in rec:
        if r.get("pop") and r.get("finish") and (r["pop"] - r["finish"]) >= 5:
            pts += 10; why.append(f"穴実績({r['pop']}人気→{r['finish']}着)"); break

    # 5) 斤量(軽いほど有利)
    w, avg = to_f(h.get("weight")), race.get("_avg_weight")
    if w and avg and avg - w >= 1.0:
        pts += (avg - w) * 2.0; why.append(f"斤量-{avg-w:.1f}kg")

    # 6) 脚質×バイアス(控えめ)
    bias, st = race.get("bias"), h.get("style") or ""
    if bias == "前" and ("逃" in st or "先" in st): pts += 4; why.append("前有利×先行")
    elif bias == "差" and ("差" in st or "追" in st): pts += 4; why.append("差有利×差し")

    return round(pts, 1), why


def main():
    race = json.load(open(sys.argv[1], encoding="utf-8"))
    hs = race["horses"]
    ws = [to_f(h.get("weight")) for h in hs if to_f(h.get("weight"))]
    race["_avg_weight"] = sum(ws) / len(ws) if ws else None

    rows = []
    for h in hs:
        if not h.get("popularity") or h["popularity"] < MIN_POP: continue
        s, why = score(h, race)
        rows.append({"num": h["num"], "name": h["name"], "pop": h["popularity"],
                     "score": s, "why": why})
    rows.sort(key=lambda x: -x["score"])

    print(f"■ 大穴ファインダー {race['date']} {race['track']}{race['raceNo']}R {race['name']} "
          f"({race['surface']}{race['distance']}m / 馬場{race.get('trackCondition','?')})")
    print(f"  {MIN_POP}番人気以下の{len(rows)}頭を、実測で有効だったシグナルのみで採点\n")
    print(f"{'順':>2} {'馬番':>3} {'馬名':<12} {'人気':>3} {'点':>6}  根拠")
    print("-" * 100)
    for i, r in enumerate(rows, 1):
        mark = "◆狙い" if r["score"] >= 30 else ("△押さえ" if r["score"] >= 18 else "")
        print(f"{i:>2} {r['num']:>3} {r['name']:<12} {r['pop']:>3} {r['score']:>6.1f}  "
              f"{' / '.join(r['why']) or '-'} {mark}")
    print("\n◆狙い(30点以上)=複勝圏率が跳ね上がる層。三連複の3列目・ワイド相手に必ず入れる。")
    print("  該当ゼロなら『この race に妙味の穴は居ない』と判断し、穴買い目を薄くする。")


if __name__ == "__main__":
    main()
