#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""妙味馬スクリーナー: 人気を一切見ずに地力を採点し、"人気とのズレ"が大きい馬を炙り出す。

JACK指摘(2026-07-19)「人気馬を集めるだけの予想なら誰でもできる。低人気馬の過去データや
相性から"этは入りそう"という提案が無い」への回答。

採点は完全にオッズ非依存。人気は最後に「妙味＝地力順位 vs 人気順位のズレ」を出す時だけ使う。

使い方: python3 tools/value_finder.py tools/racecards/2026-07-19-kokura.json
"""
import sys, json
from datetime import date as _date

# ⚠ データはローマ数字(GI/GII/GIII)とアラビア数字(G1/G2/G3)が混在する。両方必ず持たせること。
# 2026-08-15まで G1(15件)・G2(17件)・G1(地方交流)(1件)が表に無く、既定の55点に潰れていた。
# G1の実績が「クラス不明」と同点に評価される致命的な取りこぼしだったので恒久対応する。
CLASS = {"GI":100,"G1":100,"GII":90,"G2":90,"GIII":80,"G3":80,"L":72,"OP":68,
         "JpnI":92,"Jpn1":92,"JpnII":84,"Jpn2":84,"JpnIII":74,"Jpn3":74,
         # 障害は平地より層が薄く、同じ格付けでも要求水準が下。平地GIと同点にしない。
         "J・GI":86,"J・G1":86,"J・GII":78,"J・G2":78,"J・GIII":70,"J・G3":70,
         "JGI":86,"JGII":78,"JGIII":70,
         "3勝":60,"2勝":50,"1勝":42,"新馬":35,"未勝利":33,"地方重賞":45,"地方認定":30}

def cls_base(g):
    """最長一致で採点。'GIII'が'GI'に先食いされる不具合を防ぐため長いキーから照合。"""
    if not g: return 55
    s = str(g)
    for k in sorted(CLASS, key=len, reverse=True):
        if k in s: return CLASS[k]
    return 55

def to_f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

NEUTRAL = 55.0   # cls_base の既定値＝"情報が無い馬"の水準

def _days_between(a, b):
    try:
        ya,ma,da = map(int, str(a)[:10].split("-")); yb,mb,db = map(int, str(b)[:10].split("-"))
        return (_date(ya,ma,da) - _date(yb,mb,db)).days
    except Exception:
        return None

def recency(v, race_date, rec_date):
    """古い戦績は"今の地力"の証拠として弱いので、評価値を平均(NEUTRAL)へ回帰させる。

    2026-08-16 中京記念の2ファントムシーフは recent3 が全て2023年(ダービー/菊花賞/神戸新聞杯)で、
    減衰が無いと3年前のG1/G2成績で地力上位に来てしまう。休み明けそのものへの減点ではない
    (パイロマンサーの4.5ヶ月明け2着の通り、休み明けを理由に下げるのは誤り)。
    150日程度の通常のローテーションは無傷にし、1年超だけ大きく割り引く。
    ※14鞍のバックテストでは該当馬が上位に来ず差が出なかった=効果は未実証。
    """
    d = _days_between(race_date, rec_date)
    if d is None: return v
    f = 1.0 if d <= 180 else (0.7 if d <= 365 else 0.4)
    return NEUTRAL + (v - NEUTRAL) * f

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
    """着順評価。'中止'/'除外'など非数値は能力の情報が無いので中立(0)にする。
    ここを int 前提にしていると 10アドマイヤテラ(JC中止)のような馬で例外落ちする。"""
    if f is None: return -5.0
    if not isinstance(f, int): return 0.0
    return {1:12.0,2:8.0,3:5.0,4:2.0,5:1.0}.get(f, -3.0 if f<=9 else -8.0)

def margin_adj(m, finish=None):
    """着差評価。データにより勝ち馬の着差符号が±混在するため、符号に依存せず
    finish==1は勝ちとして扱い、それ以外は着差の絶対値(=着順差)で近さを見る。"""
    m=to_f(m)
    if m is None: return 0.0
    if finish == 1: return 6.0     # 勝ち(勝ち幅の符号は問わない)
    a = abs(m)
    if a <= 0.3: return 5.0
    if a <= 0.6: return 3.0
    if a <= 1.0: return 1.0
    if a <= 2.0: return -2.0
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
            + margin_adj(r.get("margin"), r.get("finish")) + agari_adj(to_f(r.get("last3f")), r.get("surface") or surface)
        fld = r.get("field")
        if isinstance(fld,int): v += (fld-8)*0.5      # 少頭数の勝ちは割引/多頭数は加点
        v = recency(v, race.get("date"), r.get("date"))
        num += v*W[i]; den += W[i]
    parts["近走地力"] = round(num/den,1) if den else 40.0

    # 2) 惜敗の連続(着順は悪いが着差僅少)＝ "足りないだけ" の馬を拾う最重要シグナル
    near = sum(1 for r in rec if (to_f(r.get("margin")) is not None
               and 0 < abs(to_f(r.get("margin"))) <= 0.6
               and 4 <= (r.get("finish") if isinstance(r.get("finish"), int) else 99) <= 8))
    parts["惜敗継続"] = 8.0 if near >= 2 else (3.0 if near == 1 else 0.0)

    # 2.5) 勢い(前走勝ち＝昇級/連勝の上昇度。過去クラス基準の地力では拾えない"上がり馬"を評価)
    last = rec[0] if rec else None
    mom = 0.0
    if last and last.get("finish") == 1:
        mom = 5.0
        m0 = to_f(last.get("margin"))
        if m0 is not None and abs(m0) >= 0.3: mom += 3.0   # 楽勝はさらに上積み(符号非依存)
    parts["勢い"] = mom

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
            if f==1: cb=max(cb,8.0)
            elif f in (2,3): cb=max(cb,5.0)
            elif f in (4,5): cb=max(cb,2.0)
    parts["コース相性"] = cb

    # 5) 脚質×今日のバイアス
    bias = race.get("_bias")   # "前" or "差"
    st = h.get("style") or ""
    sb = 0.0
    if bias=="前":
        if "逃" in st: sb=4.0
        elif "先" in st: sb=3.0
        elif "追" in st: sb=-4.0
        elif "差" in st: sb=-1.0
    elif bias=="差":
        if "追" in st or "差" in st: sb=3.0
        elif "逃" in st: sb=-2.0
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
    n = len(rows)
    for r in rows:
        gap = (r["pop"] - r["rank"]) if r["pop"] else 0
        # 人気≤5なのにスクリーナー下位=地力を取りこぼしている疑い(finish破損等)。押さえ必須。
        if r["pop"] and r["pop"] <= 5 and gap <= -5:
            flag = "⚠人気地力乖離:データ要確認/押さえ"
        elif gap >= 3:
            flag = "★妙味"
        elif gap >= 0:
            flag = "・"
        else:
            flag = "  人気先行"
        pt = r["parts"]
        det = f"地力{pt['近走地力']:.0f} 惜敗{pt['惜敗継続']:.0f} 勢い{pt.get('勢い',0):.0f} 斤{pt['斤量']:+.0f} コース{pt['コース相性']:.0f} 脚質{pt['脚質×馬場']:+.0f}"
        print(f"{r['rank']:>3} {str(r['pop']):>3} {gap:>+4}  {r['num']:>3} {r['name']:<12} {r['weight']:>4} {str(r['style'] or '-'):<3} {r['score']:>6.1f}  {det} {flag}")
    print("\n★妙味 = 地力順位が人気順位より3つ以上上（＝市場が過小評価）。ここから印を検討する。")

if __name__ == "__main__":
    main()
