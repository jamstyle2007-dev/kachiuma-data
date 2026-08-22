#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出馬表(racecard) 1件 → races.json の race エントリ 1件を機械的に組み立てる。

  python3 tools/build_entry.py tools/racecards/<file>.json            # 人が読む形で表示
  python3 tools/build_entry.py tools/racecards/<file>.json --json     # エントリJSONを出力

方針:
  - 印・主要買い目は make_marks.build()（人の裁量なし・オッズ非依存）をそのまま使う
  - make_marks が出さない券種（単勝/三連複/三連単など）は印から機械的に組む。人気・オッズは見ない
  - 根拠文(summary)・各馬の分析(analysis)は採点の内訳と近3走の"実データ"だけで書く。
    取れていない項目は書かない（捏造禁止）
  - 自信度は「地力1位と2位の差」と「1位の近走の安定度」から機械的に決める
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_finder import score_horse, to_f
import longshot_finder as lf
import make_marks

TRACK_SLUG = {"札幌":"sapporo","函館":"hakodate","福島":"fukushima","新潟":"niigata","東京":"tokyo",
              "中山":"nakayama","中京":"chukyo","京都":"kyoto","阪神":"hanshin","小倉":"kokura"}

def race_id(card):
    return f"{card['date'].replace('-','')}-{TRACK_SLUG.get(card['track'], card['track'])}-{card['raceNo']}"

def grade_short(g):
    if not g: return "OP"
    s = str(g)
    for k, v in (("GIII","G3"),("GII","G2"),("GI","G1"),("G3","G3"),("G2","G2"),("G1","G1")):
        if k in s: return v
    if "L" == s or "リステッド" in s or s.startswith("L"): return "L"
    if "オープン" in s or "OP" in s: return "OP"
    if "3勝" in s: return "3勝"
    if "2勝" in s: return "2勝"
    if "1勝" in s: return "1勝"
    return s[:4]

def fmt_run(r):
    """近走1件を事実だけで1文に"""
    if not r: return None
    parts = []
    name = r.get("race") or "?"
    g = r.get("grade")
    parts.append(f"{name}" + (f"({g})" if g else ""))
    if r.get("finish") is not None:
        fin = r["finish"]
        f_txt = f"{fin}着" if isinstance(fin, int) or str(fin).isdigit() else str(fin)
        if r.get("field"): f_txt += f"/{r['field']}頭"
        parts.append(f_txt)
    if r.get("margin") not in (None, ""): parts.append(f"着差{r['margin']}")
    if r.get("last3f"): parts.append(f"上がり{r['last3f']}")
    if r.get("distance") and r.get("surface"): parts.append(f"{r['surface']}{r['distance']}m")
    return " ".join(parts)

def rating_from_score(val, scale):
    """採点内訳の値を ◎○▲△ に丸める（scale=その項目の目安上限）"""
    if val is None: return "△"
    x = val / scale if scale else 0
    if x >= 0.75: return "◎"
    if x >= 0.45: return "○"
    if x >= 0.15: return "▲"
    return "△"

def build(card):
    hs = card["horses"]
    ws = [to_f(h.get("weight")) for h in hs if to_f(h.get("weight"))]
    card["_avg_weight"] = sum(ws) / len(ws) if ws else None
    card["_bias"] = card.get("bias")

    # 採点
    scored = []
    for h in hs:
        s, why = score_horse(h, card)
        scored.append((s, h, why))
    scored.sort(key=lambda x: -x[0])
    rank = {h["num"]: i + 1 for i, (s, h, w) in enumerate(scored)}
    by_num = {h["num"]: (s, h, w) for s, h, w in scored}

    # 印・主要買い目（裁量なし）
    ability, honsen, nerai, marks, safe_plan, long_plan = make_marks.build(card)
    plans = {"safe": dict(safe_plan), "longshot": dict(long_plan)}
    sign = {m["num"]: m["sign"] for m in marks}
    honmei = next(m["num"] for m in marks if m["sign"] == "◎")
    taikou = next((m["num"] for m in marks if m["sign"] == "○"), None)
    tan_an = next((m["num"] for m in marks if m["sign"] == "▲"), None)
    sankaku = [m["num"] for m in marks if m["sign"] == "△"]

    # 大穴ファインダー
    longs = []
    for h in hs:
        if not h.get("popularity") or h["popularity"] < lf.MIN_POP: continue
        s, why = lf.score(h, card)
        if s >= lf.THRESHOLD: longs.append((s, h["num"], h["name"], why))
    longs.sort(key=lambda x: -x[0])
    ana_num = longs[0][1] if longs else None

    # ---- 足りない券種を印から機械的に補う（人気は見ない） ----
    def ensure(plan, key, obj):
        cur = plan.get(key)
        empty = (not cur) or (not cur.get("horses") and not cur.get("combos"))
        if empty: plan[key] = obj
    safe = plans.setdefault("safe", {}); lng = plans.setdefault("longshot", {})
    base3 = [x for x in [honmei, taikou, tan_an] if x is not None]
    ensure(safe, "tansho", {"horses": [honmei], "comment": "◎（地力1位）の単勝。"})
    ensure(safe, "fukusho", {"horses": base3[:2], "comment": "◎○の複勝。"})
    ensure(safe, "sanrenpuku", {"combos": [sorted([honmei, taikou, x]) for x in ([tan_an] + sankaku[:2]) if x is not None and taikou is not None][:3],
                                "comment": "◎○を軸に▲△へ。"})
    ensure(safe, "sanrentan", {"combos": [[honmei, taikou, tan_an], [taikou, honmei, tan_an]] if taikou and tan_an else [],
                               "comment": "◎○折り返し→▲。"})
    # 穴側: 大穴ファインダー該当が無ければ地力4〜6位から
    an_core = ana_num if ana_num is not None else (sankaku[0] if sankaku else None)
    ensure(lng, "tansho", {"horses": [an_core] if an_core is not None else [],
                           "comment": ("大穴ファインダー該当馬の単勝。" if ana_num is not None else "地力4位以下で印を回した馬の単勝。該当が薄いので1点のみ。")})
    ensure(lng, "fukusho", {"horses": [x for x in [an_core] if x is not None], "comment": "穴側の複勝。"})
    ensure(lng, "wide", {"combos": [[an_core, honmei]] if an_core is not None else [], "comment": "穴から◎へのワイド。"})
    ensure(lng, "sanrenpuku", {"combos": [sorted([an_core, honmei, taikou])] if (an_core is not None and taikou) else [],
                               "comment": "◎○に穴を絡めた1点。"})
    ensure(lng, "sanrentan", {"combos": [[honmei, an_core, taikou]] if (an_core is not None and taikou) else [],
                              "comment": "◎→穴→○の1点。"})
    # 空のワイドは載せない（推奨できる時だけ表示する方針）
    for p in (safe, lng):
        if "wide" in p and not p["wide"].get("combos"): p.pop("wide")

    # ---- 自信度（機械的） ----
    s1 = scored[0][0]; s2 = scored[1][0] if len(scored) > 1 else s1
    gap = s1 - s2
    top_runs = [r for r in (scored[0][1].get("recent3") or []) if isinstance(r.get("finish"), int)]
    stable = bool(top_runs) and all(r["finish"] <= 5 for r in top_runs)
    conf = "A" if (gap >= 6 and stable) else ("B" if (gap >= 2 or stable) else "C")

    # ---- 根拠文（事実だけ） ----
    def hname(n): return by_num[n][1]["name"]
    h1 = scored[0][1]; w1 = scored[0][2]
    lines = []
    lines.append(f"{hname(honmei)}が地力{s1:.1f}で1位（2位{hname(scored[1][1]['num'])}{s2:.1f}との差{gap:.1f}）。")
    r1 = fmt_run((h1.get("recent3") or [None])[0])
    if r1: lines.append(f"前走は{r1}。")
    if (h1.get("recent3") or [])[1:2]:
        r2 = fmt_run(h1["recent3"][1])
        if r2: lines.append(f"その前は{r2}。")
    if ana_num is not None:
        lines.append(f"大穴ファインダーは{ana_num}{hname(ana_num)}（{'・'.join(longs[0][3])}）を本線に挙げた。")
    else:
        lines.append("大穴ファインダーの該当馬は無く、穴側は絞った。")
    ct = str(card.get("conditionType") or "")
    ct_short = next((k for k in ("ハンデ", "別定", "定量", "馬齢") if k in ct), "")
    if ct_short: lines.append(f"条件は{ct_short}、{card.get('fieldSize') or len(hs)}頭立て。")
    lines.append("印はオッズを見ずに地力順で付け、人気は妙味の判定にだけ使っている。")
    summary = "".join(lines)

    # ---- 各馬の分析（上位5頭＋穴） ----
    analysis = []
    targets = [h["num"] for s, h, w in scored[:5]]
    if ana_num is not None and ana_num not in targets: targets.append(ana_num)
    for n in targets:
        s, h, w = by_num[n]
        factors = []
        factors.append({"label": f"地力{rank[n]}位", "rating": sign.get(n, "△") if sign.get(n) in ("◎","○","▲") else rating_from_score(w.get("近走地力"), 110),
                        "note": f"採点{s:.1f}。近走地力{w.get('近走地力', 0):.1f}" + (f"、惜敗継続+{w['惜敗継続']:.0f}" if w.get("惜敗継続") else "") + (f"、勢い+{w['勢い']:.0f}" if w.get("勢い") else "") + "。"})
        r = (h.get("recent3") or [None])[0]
        if r and fmt_run(r): factors.append({"label": "前走", "rating": "○" if isinstance(r.get("finish"), int) and r["finish"] <= 3 else ("▲" if isinstance(r.get("finish"), int) and r["finish"] <= 6 else "△"), "note": fmt_run(r) + "。"})
        if w.get("斤量") not in (None, 0): factors.append({"label": "斤量", "rating": "○" if w["斤量"] > 0 else "△", "note": f"斤量{h.get('weight')}kg（平均比の補正{w['斤量']:+.1f}）。"})
        if w.get("コース相性"): factors.append({"label": "コース相性", "rating": rating_from_score(w["コース相性"], 10), "note": f"同コース実績の補正+{w['コース相性']:.0f}。"})
        if w.get("脚質×馬場"): factors.append({"label": "脚質×馬場", "rating": rating_from_score(w["脚質×馬場"], 10), "note": f"脚質{h.get('style') or '不明'}。馬場との相性補正+{w['脚質×馬場']:.0f}。"})
        if ana_num == n:
            factors.append({"label": "大穴ファインダー", "rating": "◎", "note": "・".join(longs[0][3]) + "。"})
        analysis.append({"num": n, "factors": factors[:4]})

    entry = {
        "id": race_id(card),
        "date": card["date"], "track": card["track"], "raceNo": card["raceNo"],
        "name": card["name"], "grade": grade_short(card.get("grade")),
        "surface": card.get("surface") or "芝", "distance": card.get("distance") or 0,
        "postTime": card.get("postTime") or "",
        "horses": [{"num": h["num"], "name": h["name"], "jockey": h.get("jockey") or ""} for h in hs],
        "prediction": {"confidence": conf, "summary": summary, "marks": marks, "analysis": analysis, "plans": plans},
    }
    return entry

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    card = json.load(open(sys.argv[1]))
    e = build(card)
    if "--json" in sys.argv:
        print(json.dumps(e, ensure_ascii=False, indent=1))
    else:
        p = e["prediction"]
        print(f"■ {e['date']} {e['track']}{e['raceNo']}R {e['name']}({e['grade']}) 自信度{p['confidence']}")
        print("  印:", " ".join(f"{m['sign']}{m['num']}" for m in p["marks"]))
        print("  根拠:", p["summary"])
        for k in ("safe", "longshot"):
            print(f"  [{k}]", {kk: (v.get('horses') or v.get('combos')) for kk, v in p["plans"][k].items()})
