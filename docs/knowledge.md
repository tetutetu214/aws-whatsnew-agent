# knowledge.md — aws-whatsnew-agent

## 決定事項
- 2026-07-01: プロジェクト名を aws-whatsnew-agent に決定。GitHub Private で作成。
- 2026-07-01: Phase を分割。Phase1 = 決定論パイプライン（LINE 送信）、Phase2 = エージェント化（未設計）。
- 2026-07-01: MCP は開発時のみ使用。Phase1 本番には組み込まない（RSS / Bedrock を直接呼ぶ）。

## 知見 / ハマり
- Codex CLI 0.130.0 は画像生成に対応（`codex features list` に image_generation stable）。
  - コマンド: `codex exec --model gpt-5.5 --sandbox workspace-write --skip-git-repo-check "..." < /dev/null`
  - 画像は `~/.codex/generated_images/<uuid>/` に出力。日本語文字も崩れず描画できた実績あり。
  - 画像生成実験（gen_image.sh）は別ディレクトリ `~/projects/aws-whatnew-visual/` にある。Phase2 の図解自動生成の原型になり得る。

## 参考（既存プロジェクト）
- daily-news-line-notifier: HuggingFace 論文を GitHub Actions cron で LINE Push。骨格を流用可能。
- 20250915_get_awsnews: What's New RSS → Bedrock 要約の PoC（4ブロック要約）。
