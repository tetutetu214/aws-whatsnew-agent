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

## 学習済み概念（理解度テスト正解済み・次回スキップ可）
- 2026-07-06: CDK の本質 = Python コードを CloudFormation テンプレートに synth して deploy する（プログラミング言語で IaC を書ける）。
- 2026-07-06: DynamoDB 冪等 + SEED_MODE の目的 = 何度実行しても二重送信せず、初回の過去記事一斉送信も防ぐ。
- 2026-07-06: Bedrock ON_DEMAND を選ぶ理由 = モデルID を直接呼べ、INFERENCE_PROFILE 必須モデルのようなクロスリージョン推論プロファイル ARN の事前作成が不要。

## 実測メモ
- 2026-07-06: us-east-1 の Nova 可用性を確認。`amazon.nova-lite-v1:0` と `amazon.nova-micro-v1:0` は ON_DEMAND 対応（推論プロファイル不要で Converse 直呼び出し可）。`amazon.nova-2-lite-v1:0` は INFERENCE_PROFILE 必須。短い日本語要約なので Nova Micro を第一候補、品質不足なら Lite に上げる。

## 知見 / ハマり
- 2026-07-04: PR #1 の Fable レビューで検出・修正した4件。①`astimezone()` 引数なしは実行環境のローカルTZ に変換されるため、Lambda(UTC) では朝7時JST実行時にヘッダーが前日日付になる → JST 固定オフセット(+9)で修正（JST は夏時間なし、tzdata 依存も回避）。②Lambda タイムアウト60秒は記事滞留日（re:Invent 期等）に直列 Bedrock 要約が超過→全滅→翌日も全滅のループリスク → 300秒に引き上げ。③未使用 `dynamodb:BatchGetItem` 権限を削除。④Bedrock ARN の us-east-1 ハードコードを self.region に統一。
- 2026-07-04: snap 版 gh は `gh pr merge` 不可のため `gh api repos/.../pulls/1/merge -X PUT -f merge_method=merge` でマージ（既知の回避策）。
- 2026-07-06: What's New RSS は1回で100件返る。SEED_MODE 無しの初回実行だと100件を要約＆Push してしまうため、初回 SEED_MODE=true の既読化が必須と実測で裏付け。
- 2026-07-06: RSS の description は `<p>` 等の HTML タグ入り。要約入力を汚さないよう rss.py でタグ除去＋エンティティ復号＋空白整形を実施。
- 2026-07-06: `python app.py` を CDK CLI 無しで直接叩くと cdk.out が出ない（標準出力先が temp になる）。synth 検証は `cdk synth`、または App(outdir='cdk.out') を明示して呼ぶ。
- 2026-07-06: Bedrock Converse API の呼び出し権限は `bedrock:InvokeModel`。ON_DEMAND 基盤モデルの ARN はアカウント無し（`arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-*`）。

- Codex CLI 0.130.0 は画像生成に対応（`codex features list` に image_generation stable）。
  - コマンド: `codex exec --model gpt-5.5 --sandbox workspace-write --skip-git-repo-check "..." < /dev/null`
  - 画像は `~/.codex/generated_images/<uuid>/` に出力。日本語文字も崩れず描画できた実績あり。
  - 画像生成実験（gen_image.sh）は別ディレクトリ `~/projects/aws-whatnew-visual/` にある。Phase2 の図解自動生成の原型になり得る。

## 参考（既存プロジェクト）
- daily-news-line-notifier: HuggingFace 論文を GitHub Actions cron で LINE Push。骨格を流用可能。
- 20250915_get_awsnews: What's New RSS → Bedrock 要約の PoC（4ブロック要約）。
