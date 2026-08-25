#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""印(◎○▲△)と買い目を出馬表から機械的に生成する。人間の裁量を一切挟まない。

なぜ作ったか(2026-08-16):
  結果の出た17鞍で、機械の地力1位は複勝圏率41%・複回収109%だったのに対し、
  私が実際に打った◎は18%・29%しかなかった。17鞍中12鞍で機械の1位を別馬に上書きしており、
  その12鞍の複勝圏率は 私の◎ 2/12 に対し 機械1位 6/12。
  「読み」で上書きするたびに成績が落ちていたので、印の決定から裁量を外す。

使い方:
  python3 tools/make_marks.py tools/racecards/<file>.json          # 印と買い目を表示
  python3 tools/make_marks.py tools/racecards/<file>.json --json   # races.json 用のJSONを出力

方針(バックテストの実測に基づく):
  ◎ = 地力1位 / ○ = 地力2位 / ▲ = 地力3位 / △ = 地力4-5位 + 大穴ファインダーの最上位。

⚠ 2026-08-23時点(検体23鞍・重複排除後)の実測。標本が小さく数字は毎週動く:
  ◆◆本線(35点以上)の複勝  204%(5/11)  ← 最も良い
  大穴◆の複勝             154%(7/22)
  地力1位の単勝            114%(的中2回のみ・当てにならない)
  地力1位の複勝             91%  ← 100%割れ。「安定してプラス」は誤りだった
  地力2位の複勝             78%
  三連複 ◎○▲1点           67%  / ◎軸6点 33%
  → 三連複を手堅い側から外した判断は23鞍では正しい(8/23新潟2歳Sで◎○▲が
     1-2-3着し1,540円を取り逃したが、通算では見送りが正解)。
"""
import sys, json, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from value_finder import score_horse, to_f
import longshot_finder as lf


def build(card):
    hs = card["horses"]
    ws = [to_f(h.get("weight")) for h in hs if to_f(h.get("weight"))]
    card["_avg_weight"] = sum(ws) / len(ws) if ws else None
    card["_bias"] = card.get("bias")

    ability = sorted(((score_horse(h, card)[0], h["num"], h["name"], h.get("popularity"))
                      for h in hs), key=lambda x: -x[0])

    longs = []
    for h in hs:
        if not h.get("popularity") or h["popularity"] < lf.MIN_POP: continue
        s, why = lf.score(h, card)
        longs.append((s, h["num"], h["name"], h["popularity"], why))
    longs.sort(key=lambda x: -x[0])
    honsen = [x for x in longs if x[0] >= lf.HONSEN]
    nerai = [x for x in longs if lf.THRESHOLD <= x[0] < lf.HONSEN]

    marks, used = [], set()
    for sign, i in (("◎", 0), ("○", 1), ("▲", 2)):
        if len(ability) > i:
            marks.append({"sign": sign, "num": ability[i][1]}); used.add(ability[i][1])
    # △は「大穴ファインダーの本線」を地力4-5位より優先する(本線は複勝圏率67%の層)
    for x in honsen + nerai:
        if len(marks) >= 6: break
        if x[1] not in used: marks.append({"sign": "△", "num": x[1]}); used.add(x[1])
    for s, num, nm, pop in ability[3:]:
        if len(marks) >= 6: break
        if num not in used: marks.append({"sign": "△", "num": num}); used.add(num)

    a = [x[1] for x in ability]
    dias = [x[1] for x in honsen + nerai]
    others = [m["num"] for m in marks if m["sign"] == "△"]

    def combos3(axis, seconds, thirds, cap=5):
        out = []
        for s in seconds:
            for t in thirds:
                c = sorted({axis, s, t})
                if len(c) == 3 and c not in out: out.append(c)
                if len(out) >= cap: return out
        return out

    # 買い目は「17鞍の実測でプラスだったものだけ」に絞る。
    #   大穴◆の複勝 212% / 地力1位の複勝 109% / 地力2位の複勝 62% / 地力3位の複勝 66%
    #   三連複(◎軸5点) 35% ← 8,500円投じて2,950円。損失のほぼ全てがここだった。
    # よって複勝を主力にし、三連複は「当たれば大きい」保険として最小限だけ残す。
    safe = {
      "fukusho": {"horses": [a[0]],
        "comment": "◎(地力1位)の複勝。ただし23鞍の実測で回収率91%と100%を割っており、プラスの根拠は無い。当方の指標で最も的中数が多い(9/23)ため軸としては置くが、厚く張る対象ではない。"},
      "wide": {"combos": [[a[0], a[1]], [a[0], a[2]]],
        "comment": "◎から○▲へのワイド2点。"},
      # アプリのスキーマは tansho/fukusho/sanrenpuku/sanrentan の4つを必須にしているため、
      # 「買わない」場合も空配列で必ずキーを出す(validate.pyがキー欠落で落ちる)。
      "tansho": {"horses": [],
        "comment": "◎の単勝は見送る。地力1位の勝率は23鞍で9%しかなく、回収率114%も的中2回だけで作られており当てにならない。"},
      "sanrenpuku": {"combos": [],
        "comment": "◎軸の三連複は見送る。23鞍で◎○▲1点=67%、◎軸6点=33%といずれも100%割れ。8/23新潟2歳Sで◎○▲が1-2-3着し1,540円を取り逃したが、通算では見送りが正しい。"},
      "sanrentan": {"combos": [],
        "comment": "三連単は見送る。当方の指標で的中実績がない。"},
    }
    # 三連複は手堅い側から外した。17鞍で◎軸5点=回収率35%、2点に絞っても的中ゼロ。
    # 多点買いは"エッジのある側"に置く方が理に適うので、大穴ファインダー軸のみに残す。
    if dias:
        longshot = {
          "fukusho": {"horses": dias[:2],
            "comment": "大穴ファインダー該当馬の複勝。23鞍の実測で回収率154%、うち◆◆本線(35点以上)に限れば204%(5/11)と全買い目中で最も良い。ここを穴側の主力に据える。"},
          "wide": {"combos": [[d, a[0]] for d in dias[:2]],
            "comment": "穴から◎へのワイド。"},
          "tansho": {"horses": [dias[0]],
            "comment": "大穴ファインダー最上位の単勝。的中は少ないが配当が大きい(17鞍で2回的中)。"},
          "sanrenpuku": {"combos": combos3(dias[0], [a[0], a[1]], a[:4], cap=2),
            "comment": "三連複は大穴◆を軸にした2点だけ。◎軸の三連複は21鞍で回収率35%と負けが込んでいたため手堅い側からは外した。なおこの◆軸2点も21鞍で的中ゼロで、期待値は未確認。"},
          "sanrentan": {"combos": [],
            "comment": "三連単は見送る。当方の指標で的中実績がない。"},
        }
    else:
        longshot = {
          "fukusho": {"horses": [],
            "comment": "大穴ファインダーの該当馬がゼロ。妙味の穴が居ないと判断し、穴側は見送る。"},
          "tansho": {"horses": [], "comment": "該当馬がゼロのため見送る。"},
          "sanrenpuku": {"combos": [], "comment": "該当馬がゼロのため見送る。"},
          "sanrentan": {"combos": [], "comment": "該当馬がゼロのため見送る。"},
        }
    return ability, honsen, nerai, marks, safe, longshot


def main():
    card = json.load(open(sys.argv[1], encoding="utf-8"))
    ability, honsen, nerai, marks, safe, longshot = build(card)
    if "--json" in sys.argv:
        print(json.dumps({"marks": marks, "plans": {"safe": safe, "longshot": longshot}},
                         ensure_ascii=False, indent=1)); return
    print(f"■ {card['date']} {card['track']}{card['raceNo']}R {card['name']} — 機械生成の印")
    sign = {m["num"]: m["sign"] for m in marks}
    for i, (s, num, nm, pop) in enumerate(ability, 1):
        mk = sign.get(num, "")
        if not mk and i > 8: continue
        print(f"  地力{i:>2}位 {mk:<2} {num:>2} {nm:<12} {str(pop):>3}人気 {s:>6.1f}")
    if honsen or nerai:
        print("\n  大穴ファインダー:")
        for s, num, nm, pop, why in honsen: print(f"    ◆◆本線 {num:>2} {nm:<12} {pop}人気 {s:.1f}  {' / '.join(why)}")
        for s, num, nm, pop, why in nerai:  print(f"    ◆狙い  {num:>2} {nm:<12} {pop}人気 {s:.1f}  {' / '.join(why)}")
    else:
        print("\n  大穴ファインダー: 該当なし → 穴側は絞る")


if __name__ == "__main__":
    main()
