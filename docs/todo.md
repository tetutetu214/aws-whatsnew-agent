# todo.md — aws-whatsnew-agent

## 進行中（運用観測フェーズ）
- [ ] LINE 到達をてつてつのスマホで実機確認（2026-07-04 疎通テスト送信済み: GameLift の記事1件）
- [ ] 要約モデルの実測（Nova Micro で開始、日本語品質不足なら Lite / Claude）— 週末は新着ゼロで実データなし。週明け 7/7 朝の配信が最初の実測機会
- [ ] 【アイデア・未着手】要約品質の記録: mark_sent 時に DynamoDB へ summary + model_id を追加保存する（原文 title/link と同一レコードで突き合わせ可能・モデル切替時の実測比較の土台になる。2026-07-04 発案、LINE 到達と初期品質を確認してから実装判断）

## 完了
- [x] 2026-07-06 定期実行の観測: 7/5・7/6 とも朝7時JST に EventBridge Scheduler から Lambda が正常起動（CloudWatch Logs 確認）。両日「Found 0 unsent articles」= 週末で新着なし・重複送信防止が正しく機能。エラーなし
- [x] 2026-07-04 デプロイ・疎通: SSM SecureString 登録（PR #2 でパラメータ名修正）→ cdk deploy 成功（9リソース）→ SEED_MODE=true で100件既読化（暴発ゼロ確認）→ 1件人工新着で本番実行 sent=1・status=sent 再記録・ログにエラーなし
- [x] PR #1 レビュー・マージ（Fable レビューで JST 日付バグ等 4 件修正 → merge 済み）
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
