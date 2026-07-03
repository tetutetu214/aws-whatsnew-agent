# todo.md — aws-whatsnew-agent

## 進行中
- [ ] spec.md のてつてつ確認 → 実装着手判断

## 次（実装フェーズ）
- [ ] Nova モデルの us-east-1 可用性確認（aws bedrock list-foundation-models）
- [ ] CDK 言語の確定（Python / TypeScript）
- [ ] LINE チャネル（既存個人通知チャネル流用か新規か）決定
- [ ] CDK スタック実装（Lambda / DynamoDB / EventBridge Scheduler / IAM / SSM 参照）
- [ ] Lambda 本体実装（RSS取得→未送信判定→Nova要約→LINE Push→DynamoDB記録）
- [ ] 初回シード（SEED_MODE=true）で暴発防止の動作確認
- [ ] 要約モデルの実測（Nova で開始、品質不足なら Claude）

## 完了
- [x] プロジェクト初期化（git init, docs 骨格, CLAUDE.md）
- [x] Codex による plan.md クロスレビュー（20項目）と反映
- [x] 実行基盤の決定（AWS EventBridge+Lambda に確定）
- [x] plan.md の未決事項を確定（全件/毎朝7時JST/フィルタ後回し/DynamoDB/Nova/CDK）
- [x] spec.md 作成

## Phase 2（未着手・設計中）
- [ ] エージェント要件の洗い出し（次の議論の主題）
- [ ] AgentCore 採用可否の判断
