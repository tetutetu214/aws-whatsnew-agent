# CLAUDE.md — aws-whatsnew-agent

AWS What's New を取得・要約して LINE に届け、将来エージェント化していくプロジェクト。

## 技術スタック
- 言語: Python 3.12
- クラウド: AWS（リージョン us-east-1 予定、確定は spec.md）
- 要約: Amazon Bedrock（Claude / Nova、未確定）
- 配信: LINE Messaging API
- Phase1 実行基盤: EventBridge Scheduler + Lambda（候補。GitHub Actions cron も代替案）

## Phase
- Phase1: What's New → 要約 → LINE（決定論パイプライン。エージェント / MCP なし）
- Phase2: エージェント化（未設計。AgentCore 採用は要件確定後に判断）

## シークレット
- LINE トークン等は Git 管理外。ローカルは `~/.secrets/aws-whatsnew-agent.env`、本番は AWS 側（SSM SecureString または Secrets Manager）。
- リポジトリには `.env.example` のみを置く。

## 設計メモ
- AWS MCP は開発支援としてのみ使用。本番 Phase1 には組み込まない。

詳細は docs/plan.md, docs/spec.md を参照。
