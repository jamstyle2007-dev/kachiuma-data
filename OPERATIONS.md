# 勝ち馬ナビ データ運用ガイド

このリポジトリの `races.json` が、アプリ「勝ち馬ナビ」の全ユーザーに配信される予想データです。
アプリは起動時とプル更新時にここの `races.json` を取得します。

対象：**中央競馬（JRA）のみ**

## 毎日の流れ（半自動）

```
1. あなた  : その日の出馬表データをClaudeに渡す（テキスト/画像/URL）
2. Claude  : 予想・印・買い目を生成して races.json を更新
3. 公開     : ./publish.sh で検証 → GitHubへpush
4. アプリ   : 各ユーザーが起動 or 引っ張って更新で最新を取得
```

### 1. 渡すデータ（最低限）
1レースあたり：
- レース情報：日付・競馬場・レース番号・レース名・グレード・芝/ダート・距離・発走時刻
- 出走馬：馬番・馬名・騎手
- （任意・精度向上）人気・オッズ・前走成績・斤量・枠 など

### 3. 公開コマンド
```bash
cd ~/kachiuma-data
./publish.sh                 # 検証→commit→push（メッセージ自動）
./publish.sh "G3 函館SS更新"  # メッセージ指定も可
```
検証で1件でも問題があれば push されません（壊れたデータを配らないため）。

### 単体で検証だけしたいとき
```bash
python3 tools/validate.py races.json
```

## races.json の形式（アプリのデコード仕様）

```jsonc
{
  "meta": {
    "updatedAt": "2026-06-21",      // 表示用の更新日（必須）
    "note": "6/21（土）函館・東京・阪神" // 任意。一覧ヘッダに小さく表示
  },
  "races": [
    {
      "id": "20260621-hakodate-11", // 一意。重複不可（推奨: 日付-場-R）
      "date": "2026-06-21",
      "track": "函館", "raceNo": 11,
      "name": "函館スプリントステークス", "grade": "G3",
      "surface": "芝", "distance": 1200, "postTime": "15:45",
      "horses": [
        { "num": 5, "name": "ウマ名", "jockey": "騎手名" }
      ],
      "prediction": {
        "confidence": "A",          // A/B/C（自信度。色分け表示）
        "summary": "AI分析の根拠テキスト",
        "marks": [                  // ◎○▲△ など。num は horses に存在する馬番
          { "sign": "◎", "num": 5 }
        ],
        "analysis": [               // 主力馬の徹底分析
          { "num": 5, "factors": [
              { "label": "コース適性", "rating": "◎", "note": "コメント" }
          ] }
        ],
        "plans": {
          "safe": {                 // 🛡 手堅い
            "tansho":     { "horses": [5],            "comment": "" },
            "fukusho":    { "horses": [5, 11],        "comment": "" },
            "sanrenpuku": { "combos": [[5,11,2]],     "comment": "" },
            "sanrentan":  { "combos": [[5,11,2]],     "comment": "" }
          },
          "longshot": {             // 🎯 穴（同じ構造）
            "tansho":     { "horses": [],  "comment": "" },
            "fukusho":    { "horses": [],  "comment": "" },
            "sanrenpuku": { "combos": [],  "comment": "" },
            "sanrentan":  { "combos": [],  "comment": "" }
          }
        }
      }
    }
  ]
}
```

### 重要な約束ごと
- `marks` / `analysis` / 買い目の馬番は、その race の `horses` に存在する `num` のみ。
- `combos` は配列の配列。三連単は**着順どおり**（[1着,2着,3着]）、三連複は順不同。
- フィールドは原則すべて必須（`meta.note` だけ任意）。欠けるとアプリが読み込めず旧データのままになる。
- レースが無い日は `races: []` でよい（アプリは「公開中のレースなし」と表示）。

## 結果・配当について
レース結果（着順）と配当は**アプリの「結果検証」タブでユーザーが手入力**する設計。
このJSONには結果は含めない（予想データのみ）。
