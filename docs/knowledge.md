# knowledge.md — aws-whatsnew-agent

## 決定事項
- 2026-07-01: プロジェクト名を aws-whatsnew-agent に決定。GitHub Private で作成。
- 2026-07-01: Phase を分割。Phase1 = 決定論パイプライン（LINE 送信）、Phase2 = エージェント化（未設計）。
- 2026-07-01: MCP は開発時のみ使用。Phase1 本番には組み込まない（RSS / Bedrock を直接呼ぶ）。
- 2026-07-01: Phase1 実行基盤を AWS（EventBridge Scheduler + Lambda）に確定。「毎朝送るだけには過剰」との Codex 指摘は承知の上で、将来の Webhook 受信・エージェント化への接続と学習を優先。
- 2026-07-01: 要約モデルは Nova で開始し、品質不足なら Claude に切り替える方針。
- 2026-07-01: Codex クロスレビュー（20項目）を plan.md に反映。主な追加=状態管理（重複送信防止）、Phase1完了条件、配信フォーマット（上位N件・LINE長文対策）、AgentCore はトーンダウンして候補扱い。
- 2026-07-06: plan.md の未決事項を確定し spec.md を作成。決定=送信は上限なし全件/毎朝7時JST/フィルタは Nova 実測後に追加（初期は全件通過）/状態ストアは DynamoDB/要約は Nova(nova-lite 第一候補)で開始/IaC は CDK(Python 第一候補)。
- 2026-07-06: 「全件・フィルタ後回し」だと初回に過去記事を一斉 Push する暴発リスクがあるため、SEED_MODE(既定false) を導入。初回だけ true で既読化(status=seeded)し送らない、以降は差分のみ送る設計にした。
- 2026-07-06: CDK 言語は Python に確定（Lambda と統一）。LINE は既存の line-notify 個人通知チャネルを流用（正本 ~/.secrets/line-notify.env → SSM SecureString へ登録して Lambda 参照）。connpass/duolingo と同じ LINE に混在するのは許容。

## 知見 / ハマり
- Codex CLI 0.130.0 は画像生成に対応（`codex features list` に image_generation stable）。
  - コマンド: `codex exec --model gpt-5.5 --sandbox workspace-write --skip-git-repo-check "..." < /dev/null`
  - 画像は `~/.codex/generated_images/<uuid>/` に出力。日本語文字も崩れず描画できた実績あり。
  - 画像生成実験（gen_image.sh）は別ディレクトリ `~/projects/aws-whatnew-visual/` にある。Phase2 の図解自動生成の原型になり得る。

## 参考（既存プロジェクト）
- daily-news-line-notifier: HuggingFace 論文を GitHub Actions cron で LINE Push。骨格を流用可能。
- 20250915_get_awsnews: What's New RSS → Bedrock 要約の PoC（4ブロック要約）。
