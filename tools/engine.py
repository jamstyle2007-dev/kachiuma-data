#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""勝ち馬ナビ 素質スコア型 予想エンジン v1

方針(JACK指示 2026-07-05): オッズ・人気に惑わされない。
◎○▲△は「馬の実力スコア」だけで決める。オッズは最後に穴/危険人気の判定にのみ使う。

入力: coworkの出馬表JSON(1レース dict)。horses[].recent3 の近走データから素質を算出する。
出力: 各馬のスコア内訳・順位・推奨印・信頼度・妙味(穴)/危険人気フラグ。

実力スコアに使う要素(すべてオッズ非依存):
  1. クラス実績     … 出走クラス(グレード)×着順×頭数。上のクラスで好走ほど高評価。
  2. 着差の質       … 勝ち馬とのタイム差。僅差ほど良、大差ほど減点。
  3. 上がり(決め手) … last3f を馬場別ベースと比較。速いほど加点。
  4. 距離適性       … 今回距離と近走距離の差。
  5. 馬場(芝/ダ)適性… 今回の芝/ダと近走の一致度。
  6. コース相性     … 今回competition場での過去好走。
  7. 馬場状態適性   … 稍/重/不での過去好走(道悪巧者)。
  8. 脚質×馬場バイアス… 前有利コースは先行/逃げを加点、追込を減点。
  9. 斤量           … 軽ハンデを小幅加点(素質評価とは別軸)。
 10. 騎手           … 上位騎手の小幅加点(将来はDBの実績率に置換)。
 11. 休み明け       … 前走からの間隔が長いほど減点(素質はあっても割引)。
"""
import re, json, sys
from datetime import date

# ---- 正規化テーブル ----
CLASS_BASE = {
    'GI':100,'G1':100,'GII':86,'G2':86,'GIII':74,'G3':74,
    'JpnI':92,'JpnII':80,'JpnIII':70,
    'L':60,'OP':56,'3勝':46,'2勝':32,'1勝':20,'新馬':15,'未勝利':12,
    '地方重賞':44,'重賞(地方)':44,'地方':16,
}
JOCKEY_TIER = {  # 将来はDBの実勝率に置換。現状は小幅プライア(最大+4)
    '川田':4,'ルメール':4,'モレイラ':4,'武豊':3,'戸崎':3,'坂井':3,'松山':3,
    '横山武':3,'C.デム':3,'Mデム':3,'横山典':2,'吉田隼':2,'池添':2,'三浦':2,
    '西村淳':2,'岩田望':2,'鮫島':2,'団野':2,'北村友':2,'丹内':1,'菊沢':1,'田辺':1,
}

def _f(x, default=0.0):
    """'0.3(アンズアメ)' や 0.3 や '58.0' を float に。"""
    if x is None: return default
    if isinstance(x, (int, float)): return float(x)
    m = re.search(r'-?\d+(\.\d+)?', str(x))
    return float(m.group()) if m else default

def _surf(s):
    return '芝' if str(s).startswith('芝') else ('ダ' if str(s).startswith('ダ') else str(s)[:1])

def _classbase(g):
    if not g: return 40.0
    g = str(g)
    if g in CLASS_BASE: return CLASS_BASE[g]
    for k, v in CLASS_BASE.items():
        if k in g: return v
    return 40.0

def _jockey_bonus(name):
    n = str(name or '')
    for k, v in JOCKEY_TIER.items():
        if k in n: return v
    return 0.0

def _is_front(style):
    s = str(style or '')
    return any(t in s for t in ('逃', '先'))

def _is_closer(style):
    s = str(style or '')
    return any(t in s for t in ('追', '差')) and '先' not in s

def _front_bias(track, surf, dist):
    """簡易・前有利指数 0(差し有利)〜1(前有利)。短距離ダート/ローカル芝1200を前有利寄りに。"""
    b = 0.5
    if surf == 'ダ':
        b += 0.15
        if dist <= 1400: b += 0.15
    else:
        if dist <= 1200: b += 0.10
    if track in ('函館', '福島', '小倉', '札幌'):  # 小回り・前残りしやすい
        b += 0.10
    return max(0.0, min(1.0, b))

def _parse_date(s):
    try:
        y, m, d = map(int, str(s).split('-')[:3]); return date(y, m, d)
    except Exception:
        return None

def _perf(pr, today_surf):
    """1近走のパフォーマンス点。"""
    cb = _classbase(pr.get('grade'))
    fin = int(_f(pr.get('finish'), 18))
    fld = int(_f(pr.get('field'), 12))
    mgn = abs(_f(pr.get('margin'), 2.0))
    l3f = _f(pr.get('last3f'), 0.0)
    psurf = _surf(pr.get('surface'))
    pos_mult = max(0.12, min(1.05, 1.05 - 0.11 * (fin - 1)))
    if fin == 1:
        margin_adj = min(mgn, 1.0) * 6.0            # 完勝ボーナス
    else:
        margin_adj = -min(mgn, 3.0) * 7.0           # 負けた着差の減点
    base3f = 33.8 if psurf == '芝' else 36.8
    # 上がりは平地の妥当域(28〜45秒)のみ採用。障害の計時(13.6等)や大差負け(71.8等)の異常値は無視
    closer = max(-2.0, min(2.5, base3f - l3f)) * 5.0 if (l3f and 28.0 <= l3f <= 45.0) else 0.0
    field_adj = (fld - 8) * 0.6
    field_adj = field_adj * (1.0 if fin <= 3 else 0.3)
    # 別馬場(芝⇄ダ)の近走は決め手指標の信頼度を落とす
    if psurf and today_surf and psurf != today_surf:
        closer *= 0.4
    return cb * pos_mult + margin_adj + closer + field_adj

def score_horse(h, race):
    today_surf = _surf(race.get('surface'))
    today_dist = int(_f(race.get('distance'), 0))
    today_track = race.get('track')
    today_cond = str(race.get('trackCondition') or '')
    rdate = _parse_date(race.get('date'))
    # 取消/中止/除外など着順が数値でない近走は素質評価から除外する
    def _valid(p):
        if not p: return False
        fin = p.get('finish')
        if isinstance(fin, bool): return False
        if isinstance(fin, (int, float)): return True
        return bool(re.fullmatch(r'\s*\d+\s*', str(fin)))
    pasts = [p for p in (h.get('recent3') or []) if _valid(p)]

    if not pasts:
        return {'num': h.get('num'), 'name': h.get('name'), 'score': 0.0, 'ability': 0.0,
                'apt': 1.0, 'note': 'データ無し'}

    perfs = [_perf(p, today_surf) for p in pasts]
    rw = [1.0, 0.72, 0.5][:len(perfs)]
    wavg = sum(pf * w for pf, w in zip(perfs, rw)) / sum(rw)
    best = max(perfs)
    ability = 0.62 * wavg + 0.38 * best   # 平均力6:ピーク力4

    # ---- 今回条件への適性(乗算) ----
    apt = 1.0
    surf_match = sum(1 for p in pasts if _surf(p.get('surface')) == today_surf) / len(pasts)
    apt *= 0.85 + 0.15 * surf_match
    dd = sum(abs(int(_f(p.get('distance'), today_dist)) - today_dist) for p in pasts) / len(pasts)
    apt *= max(0.82, 1.0 - dd / 4000.0)
    if any(p.get('track') == today_track and int(_f(p.get('finish'), 18)) <= 3 for p in pasts):
        apt *= 1.05    # 当該コースで好走歴
    if today_cond in ('稍', '重', '不'):
        offs = [1 if int(_f(p.get('finish'), 18)) <= 3 else 0
                for p in pasts if str(p.get('cond') or '') in ('稍', '重', '不')]
        if offs:
            apt *= 0.95 + 0.10 * (sum(offs) / len(offs))   # 道悪巧者
    bias = _front_bias(today_track, today_surf, today_dist)
    if _is_front(h.get('style')):
        apt *= 1.0 + 0.05 * bias
    elif _is_closer(h.get('style')):
        apt *= 1.0 - 0.04 * bias
    # 休み明け(前走からの間隔)
    layoff_note = ''
    if rdate and pasts:
        pd = _parse_date(pasts[0].get('date'))
        if pd:
            gap = (rdate - pd).days
            if gap > 120:
                pen = min((gap - 120) / 600.0, 0.28)
                apt *= (1.0 - pen)
                layoff_note = f'休み明け{gap}日(-{pen*100:.0f}%)'

    weight_adj = (56.0 - _f(h.get('weight'), 56.0)) * 1.1     # 軽ハンデ小幅加点
    jockey = _jockey_bonus(h.get('jockey'))
    score = ability * apt + weight_adj + jockey
    return {
        'num': h.get('num'), 'name': h.get('name'), 'jockey': h.get('jockey'),
        'style': h.get('style'), 'weight': _f(h.get('weight'), 56.0),
        'pop': h.get('popularity'), 'odds': h.get('winOdds'),
        'ability': round(ability, 1), 'apt': round(apt, 3),
        'weight_adj': round(weight_adj, 1), 'jockey_bonus': jockey,
        'score': round(score, 1), 'layoff': layoff_note,
    }

def rank_race(race):
    scored = sorted((score_horse(h, race) for h in race['horses']),
                    key=lambda x: x['score'], reverse=True)
    for i, s in enumerate(scored):
        s['rank'] = i + 1
    # 妙味(穴)/危険人気の判定はここで初めてオッズを使う
    for s in scored:
        pop = s.get('pop')
        if pop is not None:
            if s['rank'] <= 5 and pop >= s['rank'] + 4:
                s['flag'] = 'VALUE(妙味)'      # 実力上位だが人気薄
            elif s['rank'] >= 7 and pop <= 3:
                s['flag'] = 'DANGER(危険人気)'  # 人気だが実力下位
            else:
                s['flag'] = ''
        else:
            s['flag'] = ''
    return scored

MARK_BY_RANK = {1: '◎', 2: '○', 3: '▲', 4: '△', 5: '△', 6: '△'}

def suggest_marks(scored):
    return [{'sign': MARK_BY_RANK[s['rank']], 'num': s['num']}
            for s in scored if s['rank'] in MARK_BY_RANK]

def confidence(scored):
    """1位と3位のスコア差が大きいほど自信。混戦・多頭数はC寄り。"""
    if len(scored) < 3: return 'C'
    gap = scored[0]['score'] - scored[2]['score']
    n = len(scored)
    if gap >= 12 and n <= 14: return 'A'
    if gap >= 6: return 'B'
    return 'C'

if __name__ == '__main__':
    data = json.load(open(sys.argv[1], encoding='utf-8'))
    races = data if isinstance(data, list) else [data]
    for race in races:
        scored = rank_race(race)
        print(f"\n=== {race['track']}{race.get('raceNo','')}R {race['name']} "
              f"{race.get('surface')}{race.get('distance')} {race.get('trackCondition','')} "
              f"[{race.get('conditionType','')}] 信頼度{confidence(scored)} ===")
        marks = {s['num']: MARK_BY_RANK.get(s['rank'], '') for s in scored}
        for s in scored:
            print(f"  {marks.get(s['num'],'  '):2} {s['rank']:>2}位 "
                  f"score{s['score']:>6.1f} (力{s['ability']:>5.1f}×適性{s['apt']:.2f}) "
                  f"{s['num']:>2}{s['name']}({s['jockey']}/{s.get('pop','?')}人気) "
                  f"{s['flag']}{(' '+s['layoff']) if s['layoff'] else ''}")
        r = race.get('result')
        if r:
            print(f"  結果 {r['first']}-{r['second']}-{r['third']}  "
                  f"エンジン印: {' '.join(m['sign']+str(m['num']) for m in suggest_marks(scored))}")
