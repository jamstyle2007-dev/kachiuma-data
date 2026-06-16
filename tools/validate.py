#!/usr/bin/env python3
"""races.json をアプリ(KeibaYosou)のデコード仕様どおりか検証する。
アプリは Swift Codable で読むため、必須フィールド欠落や型違いがあると
「無言で旧データのまま」になる。公開前に必ずこれを通すこと。
使い方: python3 tools/validate.py races.json
"""
import sys, json

errors = []

def err(path, msg):
    errors.append(f"  - {path}: {msg}")

def need(obj, key, typ, path):
    if key not in obj:
        err(path, f"必須キー '{key}' がありません"); return None
    v = obj[key]
    if typ is int and isinstance(v, bool):  # bool は int 扱いしない
        err(f"{path}.{key}", "整数が必要です"); return None
    if not isinstance(v, typ):
        err(f"{path}.{key}", f"型が不正（{typ.__name__} が必要）"); return None
    return v

def check_betsimple(o, path):
    if not isinstance(o, dict): err(path, "オブジェクトが必要"); return
    hs = need(o, "horses", list, path)
    if hs is not None and not all(isinstance(x, int) and not isinstance(x, bool) for x in hs):
        err(f"{path}.horses", "整数の配列が必要")
    need(o, "comment", str, path)

def check_betcombo(o, path):
    if not isinstance(o, dict): err(path, "オブジェクトが必要"); return
    cs = need(o, "combos", list, path)
    if cs is not None:
        for i, c in enumerate(cs):
            if not (isinstance(c, list) and all(isinstance(x, int) and not isinstance(x, bool) for x in c)):
                err(f"{path}.combos[{i}]", "整数配列が必要")
    need(o, "comment", str, path)

def main():
    if len(sys.argv) < 2:
        print("使い方: python3 tools/validate.py races.json"); sys.exit(2)
    try:
        data = json.load(open(sys.argv[1], encoding="utf-8"))
    except Exception as e:
        print(f"JSONとして読めません: {e}"); sys.exit(1)

    meta = need(data, "meta", dict, "root")
    if meta is not None:
        need(meta, "updatedAt", str, "meta")
        if "note" in meta and not isinstance(meta["note"], str):
            err("meta.note", "文字列が必要（任意キー）")

    races = need(data, "races", list, "root")
    if races is None:
        report(); return
    if len(races) == 0:
        print("⚠️  races が空です（アプリは『公開中のレースなし』表示になります）")

    seen_ids = set()
    for i, r in enumerate(races):
        p = f"races[{i}]"
        if not isinstance(r, dict): err(p, "オブジェクトが必要"); continue
        rid = need(r, "id", str, p)
        if rid is not None:
            if rid in seen_ids: err(f"{p}.id", f"id '{rid}' が重複")
            seen_ids.add(rid)
        for k in ("date", "track", "name", "grade", "surface", "postTime"):
            need(r, k, str, p)
        need(r, "raceNo", int, p)
        need(r, "distance", int, p)

        horses = need(r, "horses", list, p)
        nums = set()
        if horses is not None:
            for j, h in enumerate(horses):
                hp = f"{p}.horses[{j}]"
                if not isinstance(h, dict): err(hp, "オブジェクトが必要"); continue
                n = need(h, "num", int, hp)
                if n is not None: nums.add(n)
                need(h, "name", str, hp); need(h, "jockey", str, hp)

        pred = need(r, "prediction", dict, p)
        if pred is None: continue
        pp = f"{p}.prediction"
        need(pred, "confidence", str, pp)
        need(pred, "summary", str, pp)

        marks = need(pred, "marks", list, pp)
        if marks is not None:
            for j, m in enumerate(marks):
                mp = f"{pp}.marks[{j}]"
                if not isinstance(m, dict): err(mp, "オブジェクトが必要"); continue
                need(m, "sign", str, mp)
                mn = need(m, "num", int, mp)
                if mn is not None and nums and mn not in nums:
                    err(f"{mp}.num", f"馬番 {mn} が出走馬に存在しません")

        analysis = need(pred, "analysis", list, pp)
        if analysis is not None:
            for j, a in enumerate(analysis):
                ap = f"{pp}.analysis[{j}]"
                if not isinstance(a, dict): err(ap, "オブジェクトが必要"); continue
                need(a, "num", int, ap)
                facs = need(a, "factors", list, ap)
                if facs is not None:
                    for k2, f in enumerate(facs):
                        fp = f"{ap}.factors[{k2}]"
                        if not isinstance(f, dict): err(fp, "オブジェクトが必要"); continue
                        need(f, "label", str, fp); need(f, "rating", str, fp); need(f, "note", str, fp)

        plans = need(pred, "plans", dict, pp)
        if plans is not None:
            for side in ("safe", "longshot"):
                pl = need(plans, side, dict, f"{pp}.plans")
                if pl is None: continue
                base = f"{pp}.plans.{side}"
                check_betsimple(pl.get("tansho", {}), f"{base}.tansho") if "tansho" in pl else err(base, "必須キー 'tansho'")
                check_betsimple(pl.get("fukusho", {}), f"{base}.fukusho") if "fukusho" in pl else err(base, "必須キー 'fukusho'")
                check_betcombo(pl.get("sanrenpuku", {}), f"{base}.sanrenpuku") if "sanrenpuku" in pl else err(base, "必須キー 'sanrenpuku'")
                check_betcombo(pl.get("sanrentan", {}), f"{base}.sanrentan") if "sanrentan" in pl else err(base, "必須キー 'sanrentan'")

    report()

def report():
    if errors:
        print(f"❌ 検証NG: {len(errors)} 件の問題")
        print("\n".join(errors))
        sys.exit(1)
    print("✅ 検証OK: アプリが読み込める形式です")

if __name__ == "__main__":
    main()
