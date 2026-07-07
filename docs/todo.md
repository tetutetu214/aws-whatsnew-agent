# todo.md — aws-whatsnew-agent

## Phase 1.5: カテゴリフィルタ + LINE 設定・フィードバック（2026-07-08 起票、同日「集計ループまで全部入り」でスコープ確定、spec.md §9）
- [x] スコープ確定: LINE 内で設定操作 / ルール+LLM 二段判定 / 「いらない」ボタンのみ / 集計・カテゴリ追加削除・LLM 提案まで全部入り（てつてつ回答済み）
- [ ] 実装（Codex 委譲予定）: フィルタ二段判定（rules + Nova 分類）/ 動的カテゴリ（SSM filter/config）/ EXCLUDE_SERVICES 廃止 / 配信 Flex 化（1記事=1カード、5記事/リクエスト）+ 「いらない」ボタン / SettingsWebhook Lambda + Function URL（設定・集計・追加削除・提案）/ CDK 更新 / テスト
- [ ] 検収（Claude）: pytest + cdk synth、直近 RSS 実データでルール網羅率確認
- [ ] デプロイ（要 aws login）: channel_secret を SSM 登録 → cdk deploy → LINE コンソールに Webhook URL 設定
- [ ] 実機確認: 「設定」→トグル操作、「いらない」タップ→「集計」反映、翌朝配信でフィルタ効果を観測

## 進行中（運用観測フェーズ）
- [ ] 要約モデルの実測（Nova Micro で開始、日本語品質不足なら Lite / Claude）— 7/7(火) 朝から実配信データが DynamoDB に summary 付きで貯まる。初サンプル1件では敬体/常体の混在あり（knowledge.md 実測メモ参照）。数日分貯まったら品質判定

## 完了
- [x] 2026-07-06 要約品質記録の実装（PR #3）: mark_sent 時に summary + model_id を DynamoDB へ追加保存。Opus サブエージェント実装 → Fable レビュー → テスト19件パス → マージ → cdk deploy（Lambda のみ更新21秒）→ 1件 delete→invoke の実機検証で summary/model_id 保存を確認（sent=1）
- [x] 2026-07-06 LINE 到達の実機確認: 7/4 疎通テスト（GameLift 記事1件）がてつてつのスマホに到達済みと本人確認
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
