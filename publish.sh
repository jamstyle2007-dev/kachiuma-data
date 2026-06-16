#!/bin/bash
# races.json を検証して GitHub へ公開する。
# 検証NGなら push しない（壊れたデータを全ユーザーに配らないため）。
# 使い方:  ./publish.sh           （メッセージ自動）
#          ./publish.sh "コメント"  （コミットメッセージ指定）
set -e
cd "$(dirname "$0")"

echo "▶ 検証中..."
python3 tools/validate.py races.json || { echo "✋ 検証NGのため公開を中止しました。"; exit 1; }

if git diff --quiet races.json; then
  echo "（races.json に変更なし。公開するものがありません）"
  exit 0
fi

MSG="${1:-Update races.json $(date +%F)}"
git add races.json
git commit -m "$MSG"
echo "▶ push 中..."
git push
echo "✅ 公開しました。各ユーザーのアプリは次回起動／引っ張って更新で最新になります。"
