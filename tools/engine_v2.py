#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""勝ち馬ナビ 素質スコア型 予想エンジン v2

v1(engine.py)の 2026-07-12 敗因分析を反映した改良版。
- 分析: 七夕賞/阿蘇Sとも◎=1人気。着順・着差を重く見すぎて、実際は
  「近走着順は平凡だが上がり最速級の差し馬」を最下位近くに沈めていた
  (七夕賞2着=v1で8位, 3着=16位/最下位, 阿蘇S3着=9位)。
  = "オッズ非依存"のはずが事実上「人気馬再生装置」になっていた。

v2の4本柱:
  (A) ペース想定: 出走馬の脚質構成から前有利/差し有利を判定し、
      決め手・脚質適性に反映。逃げが1頭だけなら単騎逃げを加点。
  (B) 決め手(上がり)の比重UP＋着順/着差減点の緩和(上のクラスほど緩く)。
      速い上がりを継続する馬は着順が平凡でも実力を認める。
  (C) 斤量トップハンデの減点強化(小回り/ハンデで57.5kg以上)。
  (D) 休み明け: recent3にdateが無いため、出馬表の daysSince/rest を使う
      (無ければ従来どおりスキップ)。

入出力・スキーマはv1と互換。
"""
import re, json, sys
from datetime import date

CLASS_BASE = {
    'GI':100,'G1':100,'GII':86,'G2':86,'GIII':74,'G3':74,
    'JpnI':92,'JpnII':80,'JpnIII':70,
    'L':60,'OP':56,'3勝':46,'2勝':32,'1勝':20,'新馬':15,'未勝利':12,
    '地方重賞':44,'重賞(地方)':44,'地方':16,
}
JOCKEY_TIER = {
    '川田':4,'ルメール':4,'モレイラ':4,'武豊':3,'戸崎':3,'坂井':3,'松山':3,
    '横山武':3,'C.デム':3,'Mデム':3,'横山典':2,'吉田隼':2,'池添':2,'三浦':2,
    '西村淳':2,'岩田望':2,'鮫島':2,'団野':2,'北村友':2,'丹内':1,'菊沢':1,'田辺':1,
}

def _f(x, default=0.0):
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

def _static_front_bias(track, surf, dist):
    """コース固有の前有利指数 0.5(標準)〜0.9(前有利)。"""
    b = 0.5
    if surf == 'ダ':
        b += 0.15
        if dist <= 1400: b += 0.15
    else:
        if dist <= 1200: b += 0.10
    if track in ('函館', '福島', '小倉', '札幌'):   # 小回り・前残りしやすい
        b += 0.10
    return max(0.0, min(1.0, b))

# ---- (A) ペース想定 ----
def pace_context(race):
    """出走馬の脚質構成＋コースから『差し有利度』closer_fav∈[-1,+1]を返す。
    +1: 差し・追込が来やすい(ハイペース/差し決着)。-1: 前残り(前有利)。
    lone_num: 逃げが1頭だけの時その馬番(単騎逃げ)。"""
    horses = race.get('horses', [])
    n = max(1, len(horses))
    surf = _surf(race.get('surface'))
    dist = int(_f(race.get('distance'), 0))
    track = race.get('track')
    nige = [h for h in horses if '逃' in str(h.get('style'))]
    front = [h for h in horses if _is_front(h.get('style'))]
    front_share = len(front) / n
    # ペース圧力: 逃げが多い/前が渋滞するほど前が総崩れ→差し有利
    if len(nige) >= 3:   pressure = 1.0
    elif len(nige) == 2: pressure = 0.4
    elif len(nige) == 1: pressure = -0.6   # 単騎楽逃げ→前残り
    else:                pressure = -0.2   # 純逃げ不在→先行が支配
    pressure += (front_share - 0.5) * 1.2
    if surf == 'ダ':
        pressure *= 0.45   # ダートは差しが届きにくくペース恩恵が小さい
    static = _static_front_bias(track, surf, dist)
    closer_fav = pressure * 0.6 - (static - 0.5) * 1.4
    closer_fav = max(-1.0, min(1.0, closer_fav))
    lone_num = nige[0].get('num') if len(nige) == 1 else None
    return closer_fav, lone_num

def _parse_date(s):
    try:
        y, m, d = map(int, str(s).split('-')[:3]); return date(y, m, d)
    except Exception:
        return None

def _perf(pr, today_surf):
    """1近走のパフォーマンス点(v2: 決め手UP・着順/着差減点を緩和)。"""
    cb = _classbase(pr.get('grade'))
    fin = int(_f(pr.get('finish'), 18))
    fld = int(_f(pr.get('field'), 12))
    mgn = abs(_f(pr.get('margin'), 2.0))
    l3f = _f(pr.get('last3f'), 0.0)
    psurf = _surf(pr.get('surface'))
    pos_mult = max(0.20, min(1.05, 1.05 - 0.095 * (fin - 1)))   # 着順減点をやや緩和・下限UP
    # (B) 上がりが優秀な敗戦は「脚は使えている」と救済
    # 基準値は現実の平地決着に合わせる(旧33.8/36.8は速すぎて全馬が減点され機能不全だった)
    base3f = 34.8 if psurf == '芝' else 37.3
    kick = (base3f - l3f) if (l3f and 28.0 <= l3f <= 45.0) else 0.0
    if fin > 3 and kick >= 1.0:                 # 平凡着順でも上がり上位級なら
        pos_mult = max(pos_mult, 0.50)          # 沈めすぎない(差し脚の実力を認める)
    if fin == 1:
        margin_adj = min(mgn, 1.0) * 6.0
    else:
        margin_adj = -min(mgn, 3.0) * 5.5       # 7.0→5.5 に緩和(過度に沈めない)
        # 注: 「重賞の僅差負けを軽減」補正は、負けた最上位人気を増幅する副作用があり不採用
    closer = max(-2.5, min(3.0, kick)) * 6.0     # 決め手比重UP(5.0→6.0)・現実基準
    field_adj = (fld - 8) * 0.6
    field_adj = field_adj * (1.0 if fin <= 3 else 0.3)
    if psurf and today_surf and psurf != today_surf:
        closer *= 0.4
    return cb * pos_mult + margin_adj + closer + field_adj

def score_horse(h, race, ctx=None):
    today_surf = _surf(race.get('surface'))
    today_dist = int(_f(race.get('distance'), 0))
    today_track = race.get('track')
    today_cond = str(race.get('trackCondition') or '')
    cond_type = str(race.get('conditionType') or '')
    rdate = _parse_date(race.get('date'))
    if ctx is None:
        ctx = pace_context(race)
    closer_fav, lone_num = ctx

    def _valid(p):
        if not p: return False
        fin = p.get('finish')
        if isinstance(fin, bool): return False
        if isinstance(fin, (int, float)): return True
        return bool(re.fullmatch(r'\s*\d+\s*', str(fin)))
    pasts = [p for p in (h.get('recent3') or []) if _valid(p)]

    if not pasts:
        return {'num': h.get('num'), 'name': h.get('name'), 'score': 0.0, 'ability': 0.0,
                'apt': 1.0, 'note': 'データ無し', 'style': h.get('style'),
                'weight': _f(h.get('weight'),56.0), 'pop': h.get('popularity'),
                'odds': h.get('winOdds'), 'weight_adj':0.0,'jockey_bonus':0.0,'layoff':''}

    perfs = [_perf(p, today_surf) for p in pasts]
    rw = [1.0, 0.72, 0.5][:len(perfs)]
    wavg = sum(pf * w for pf, w in zip(perfs, rw)) / sum(rw)
    best = max(perfs)
    ability = 0.62 * wavg + 0.38 * best

    apt = 1.0
    surf_match = sum(1 for p in pasts if _surf(p.get('surface')) == today_surf) / len(pasts)
    apt *= 0.85 + 0.15 * surf_match
    dd = sum(abs(int(_f(p.get('distance'), today_dist)) - today_dist) for p in pasts) / len(pasts)
    apt *= max(0.82, 1.0 - dd / 4000.0)
    # コース相性: 同コースかつ同距離帯の好走はより厚く
    exact = any(p.get('track') == today_track and abs(int(_f(p.get('distance'),today_dist))-today_dist) <= 100
                and int(_f(p.get('finish'), 18)) <= 3 for p in pasts)
    same_course = any(p.get('track') == today_track and int(_f(p.get('finish'), 18)) <= 3 for p in pasts)
    if exact:        apt *= 1.09
    elif same_course: apt *= 1.05
    # 洋芝(函館/札幌)は洋芝経験が無い野芝実績馬をやや割引
    if today_track in ('函館','札幌') and today_surf == '芝':
        yoshiba = any(_surf(p.get('surface'))=='芝' and p.get('track') in ('函館','札幌') for p in pasts)
        if not yoshiba: apt *= 0.95
    if today_cond in ('稍', '重', '不'):
        offs = [1 if int(_f(p.get('finish'), 18)) <= 3 else 0
                for p in pasts if str(p.get('cond') or '') in ('稍', '重', '不')]
        if offs:
            apt *= 0.95 + 0.10 * (sum(offs) / len(offs))
    # (A) ペース×脚質(v1の±4%から強化)。有力先行を過度に消さないよう非対称にする
    #  (七夕賞の勝ち馬=逃げを潰した反省: 差しの加点は厚め、先行の減点は薄め)
    if _is_closer(h.get('style')):
        apt *= 1.0 + 0.13 * closer_fav
    elif _is_front(h.get('style')):
        apt *= 1.0 - 0.05 * closer_fav   # 有力先行を消しすぎない(逃げ切り勝ちは普通に起こる)
    if lone_num is not None and h.get('num') == lone_num:
        apt *= 1.10   # 単騎逃げは大アドバンテージ
    # (D) 休み明け: 出馬表に daysSince/rest があれば減点(recent3にdateが無い為)
    layoff_note = ''
    gap = h.get('daysSince', h.get('rest'))
    gap = int(_f(gap, 0)) if gap is not None else 0
    if gap > 120:
        pen = min((gap - 120) / 700.0, 0.22)   # やや控えめ(鉄砲成績の良い馬もいる為)
        apt *= (1.0 - pen)
        layoff_note = f'休み明け{gap}日(-{pen*100:.0f}%)'

    # (C) 斤量: 軽ハンデ加点＋トップハンデ減点強化
    w = _f(h.get('weight'), 56.0)
    weight_adj = (56.0 - w) * 1.1
    if w >= 57.5:
        extra = (w - 57.0) * 1.6
        if today_track in ('函館','福島','小倉','札幌','中山'): extra *= 1.2  # 小回りは酷量が堪える
        weight_adj -= extra
    jockey = _jockey_bonus(h.get('jockey'))
    score = ability * apt + weight_adj + jockey
    return {
        'num': h.get('num'), 'name': h.get('name'), 'jockey': h.get('jockey'),
        'style': h.get('style'), 'weight': w,
        'pop': h.get('popularity'), 'odds': h.get('winOdds'),
        'ability': round(ability, 1), 'apt': round(apt, 3),
        'weight_adj': round(weight_adj, 1), 'jockey_bonus': jockey,
        'score': round(score, 1), 'layoff': layoff_note,
    }

def rank_race(race):
    ctx = pace_context(race)
    scored = sorted((score_horse(h, race, ctx) for h in race['horses']),
                    key=lambda x: x['score'], reverse=True)
    for i, s in enumerate(scored):
        s['rank'] = i + 1
    for s in scored:
        pop = s.get('pop')
        if pop is not None:
            if s['rank'] <= 5 and pop >= s['rank'] + 4:
                s['flag'] = 'VALUE(妙味)'
            elif s['rank'] >= 7 and pop <= 3:
                s['flag'] = 'DANGER(危険人気)'
            else:
                s['flag'] = ''
        else:
            s['flag'] = ''
    return scored, ctx

MARK_BY_RANK = {1: '◎', 2: '○', 3: '▲', 4: '△', 5: '△', 6: '△'}

def suggest_marks(scored):
    return [{'sign': MARK_BY_RANK[s['rank']], 'num': s['num']}
            for s in scored if s['rank'] in MARK_BY_RANK]

def confidence(scored):
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
        scored, ctx = rank_race(race)
        closer_fav, lone = ctx
        pace_lbl = ('差し有利' if closer_fav>0.15 else ('前有利' if closer_fav<-0.15 else '中立'))
        print(f"\n=== {race['track']}{race.get('raceNo','')}R {race['name']} "
              f"{race.get('surface')}{race.get('distance')} {race.get('trackCondition','')} "
              f"[{race.get('conditionType','')}] 信頼度{confidence(scored)} "
              f"| ペース想定:{pace_lbl}({closer_fav:+.2f}){' 単騎逃'+str(lone) if lone else ''} ===")
        marks = {s['num']: MARK_BY_RANK.get(s['rank'], '') for s in scored}
        for s in scored:
            print(f"  {marks.get(s['num'],'  '):2} {s['rank']:>2}位 "
                  f"score{s['score']:>6.1f} (力{s['ability']:>5.1f}×適性{s['apt']:.2f}) "
                  f"{s['num']:>2}{s['name']}({s['jockey']}/{s.get('pop','?')}人気) "
                  f"{s['flag']}{(' '+s['layoff']) if s['layoff'] else ''}")
        r = race.get('result')
        if r:
            em = suggest_marks(scored)
            hit = {'first':r['first'],'second':r['second'],'third':r['third']}
            print(f"  結果 {r['first']}-{r['second']}-{r['third']}  "
                  f"エンジン印: {' '.join(m['sign']+str(m['num']) for m in em)}")
