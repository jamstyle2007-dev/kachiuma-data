#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""妙味馬スクリーナー: 人気を一切見ずに地力を採点し、"人気とのズレ"が大きい馬を炙り出す。

JACK指摘(2026-07-19)「人気馬を集めるだけの予想なら誰でもできる。低人気馬の過去データや
相性から"этは入りそう"という提案が無い」への回答。

採点は完全にオッズ非依存。人気は最後に「妙味＝地力順位 vs 人気順位のズレ」を出す時だけ使う。

使い方: python3 tools/value_finder.py tools/racecards/2026-07-19-kokura.json
"""
import sys, json

CLASS = {"GI":100,"GII":90,"GIII":80,"G3":80,"L":72,"OP":68,
         "3勝":60,"2勝":50,"1勝":42,"新馬":35,"未勝利":33,"地方重賞":45,"地方認定":30}

def cls_base(g):
    if not g: return 55
    for k,v in CLASS.items():
        if k in str(g): return v
    return 55

def to_f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def agari_adj(last3f, surface):
    if last3f is None: return 0.0
    if surface == "芝":
        t=[(33.5,3.0),(34.0,2.0),(34.5,1.0),(35.5,0.0)]
    else:
        t=[(36.0,3.0),(36.5,2.0),(37.0,1.0),(38.0,0.0)]
    for lim,pt in t:
        if last3f < lim: return pt
    return -2.0

def finish_adj(f):
    if f is None: return -5.0
    return {1:12.0,2:8.0,3:5.0,4:2.0,5:1.0}.get(f, -3.0 if f<=9 else -8.0)

def margin_adj(m):
    m=to_f(m)
    if m is None: return 0.0
    if m <= 0: return 6.0          # 勝ち
    if m <= 0.3: return 5.0
    if m <= 0.6: return 3.0
    if m <= 1.0: return 1.0
    if m <= 2.0: return -2.0
    return -5.0

def score_horse(h, race):
    """地力スコア(オッズ非依存)。内訳も返す。"""
    surface = race["surface"]; dist = race["distance"]; track = race["track"]
    rec = [r for r in (h.get("recent3") or []) if r]
    parts = {}

    # 1) 近走の地力(直近ほど重く)
    W=[1.0,0.8,0.6]; num=den=0.0
    for i,r in enumerate(rec[:3]):
        v = cls_base(r.get("grade")) + finish_adj(r.get("finish")) \
            + margin_adj(r.get("margin")) + agari_adj(to_f(r.get("last3f")), r.get("surface") or surface)
        fld = r.get("field")
        if isinstance(fld,int): v += (fld-8)*0.5      # 少頭数の勝ちは割引/多頭数は加点
        num += v*W[i]; den += W[i]
    parts["近走地力"] = round(num/den,1) if den else 40.0

    # 2) 惜敗の連続(着順は悪いが着差僅少)＝ "足りないだけ" の馬を拾う最重要シグナル
    near = sum(1 for r in rec if (to_f(r.get("margin")) is not None
               and 0 < to_f(r.get("margin")) <= 0.6 and (r.get("finish") or 99) >= 4))
    parts["惜敗継続"] = 8.0 if near >= 2 else (3.0 if near == 1 else 0.0)

    # 3) 斤量(軽いほど有利。ハンデ戦で効く)
    parts["斤量"] = 0.0
    w = to_f(h.get("weight")); avg = race.get("_avg_weight")
    if w and avg: parts["斤量"] = round((avg - w)*2.5, 1)

    # 4) コース相性(同競馬場×同馬場×距離±200mで3着内)
    cb = 0.0
    for r in rec:
        if r.get("track")==track and (r.get("surface") or surface)==surface \
           and r.get("distance") and abs(r["distance"]-dist)<=200:
            f=r.get("finish")
            if f==1: cb=max(cb,14.0)
            elif f in (2,3): cb=max(cb,9.0)
            elif f in (4,5): cb=max(cb,4.0)
    parts["コース相性"] = cb

    # 5) 脚質×今日のバイアス
    bias = race.get("_bias")   # "前" or "差"
    st = h.get("style") or ""
    sb = 0.0
    if bias=="前":
        if "逃" in st: sb=7.0
        elif "先" in st: sb=5.0
        elif "追" in st: sb=-5.0
        elif "差" in st: sb=-2.0
    elif bias=="差":
        if "追" in st or "差" in st: sb=5.0
        elif "逃" in st: sb=-3.0
    parts["脚質×馬場"] = sb

    return round(sum(parts.values()),1), parts

def main():
    path = sys.argv[1]
    race = json.load(open(path, encoding="utf-8"))
    hs = race["horses"]
    ws = [to_f(h.get("weight")) for h in hs if to_f(h.get("weight"))]
    race["_avg_weight"] = sum(ws)/len(ws) if ws else None
    race["_bias"] = race.get("bias")

    rows=[]
    for h in hs:
        s,p = score_horse(h, race)
        rows.append({"num":h["num"],"name":h["name"],"pop":h.get("popularity"),
                     "style":h.get("style"),"weight":h.get("weight"),"score":s,"parts":p})
    rows.sort(key=lambda x:-x["score"])
    for i,r in enumerate(rows,1): r["rank"]=i

    print(f"■ {race['date']} {race['track']}{race['raceNo']}R {race['name']} "
          f"({race['surface']}{race['distance']}m / 馬場{race.get('trackCondition','?')} / バイアス想定={race.get('bias','なし')})")
    print(f"{'地力':>3} {'人気':>3} {'ズレ':>4}  {'馬番':>3} {'馬名':<12} {'斤':>4} {'脚質':<3} {'点':>6}  内訳")
    print("-"*112)
    for r in rows:
        gap = (r["pop"] - r["rank"]) if r["pop"] else 0
        flag = "★妙味" if gap >= 3 else ("・" if gap >= 0 else "  人気先行")
        pt = r["parts"]
        det = f"地力{pt['近走地力']:.0f} 惜敗{pt['惜敗継続']:.0f} 斤{pt['斤量']:+.0f} コース{pt['コース相性']:.0f} 脚質{pt['脚質×馬場']:+.0f}"
        print(f"{r['rank']:>3} {str(r['pop']):>3} {gap:>+4}  {r['num']:>3} {r['name']:<12} {r['weight']:>4} {str(r['style'] or '-'):<3} {r['score']:>6.1f}  {det} {flag}")
    print("\n★妙味 = 地力順位が人気順位より3つ以上上（＝市場が過小評価）。ここから印を検討する。")

if __name__ == "__main__":
    main()
