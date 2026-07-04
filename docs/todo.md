# todo.md — aws-whatsnew-agent

## 進行中
- [ ] PR レビュー・マージ（feature/phase1-implementation）

## 次（デプロイ・疎通フェーズ）
- [ ] SSM に LINE トークン/USER_ID を SecureString で登録（~/.secrets/line-notify.env の値）
- [ ] cdk bootstrap（未実施なら）→ cdk deploy（us-east-1）
- [ ] 初回 SEED_MODE=true で手動実行 → 既存記事を既読化（暴発防止の実確認）
- [ ] SEED_MODE=false で手動実行 → 自分に LINE 到達を確認（200でも届かない罠に注意）
- [ ] 要約モデルの実測（Nova Micro で開始、日本語品質不足なら Lite / Claude）

## 完了
- [x] プロジェクト初期化（git init, docs 骨格, CLAUDE.md）
- [x] Codex による plan.md クロスレビュー（20項目）と反映
- [x] 実行基盤の決定（AWS EventBridge+Lambda に確定）
- [x] plan.md の未決事項を確定（全件/毎朝7時JST/フィルタ後回し/DynamoDB/Nova/CDK）
- [x] spec.md 作成
- [x] Nova の us-east-1 可用性確認（nova-micro/lite が ON_DEMAND 可）
- [x] CDK 言語確定（Python）/ LINE チャネル確定（既存流用）
- [x] Phase1 実装（Codex 委譲）: CDK スタック + Lambda(RSS/store/summarize/line) + テスト13件
- [x] ローカル検証: pytest 13件パス / cdk synth 成功 / 実 RSS 100件パース確認

## Phase 2（未着手・設計中）
- [ ] エージェント要件の洗い出し（次の議論の主題）
- [ ] AgentCore 採用可否の判断
