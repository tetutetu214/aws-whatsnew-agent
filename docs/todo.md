# todo.md — aws-whatsnew-agent

## Phase 1.5: カテゴリフィルタ + LINE 設定・フィードバック（2026-07-08 起票、同日「集計ループまで全部入り」でスコープ確定、spec.md §9）
- [x] スコープ確定: LINE 内で設定操作 / ルール+LLM 二段判定 / 「いらない」ボタンのみ / 集計・カテゴリ追加削除・LLM 提案まで全部入り（てつてつ回答済み）
- [x] 2026-07-08 実装（Codex gpt-5.5 委譲、11分で完了）: フィルタ二段判定 / 動的カテゴリ / EXCLUDE_SERVICES 廃止 / 配信 Flex 化（1記事=1カード）+ 「いらない」ボタン / SettingsWebhook Lambda + Function URL / CDK 更新 / テスト
- [x] 2026-07-08 検収（Fable レビューで 5 件修正）: ①regex `in .* regions` の誤爆を available 必須化で修正（実 RSS 100件で region 15件確定・誤爆ゼロを実測）②worker の不要な dynamodb:UpdateItem 削除 ③webhook 例外時も 200 返却（LINE 再送での二重適用防止）④Scan の 1MB ページネーション追加 ⑤除外記事のログ追加。pytest 60件パス / cdk synth 成功。Codex サンドボックスに pytest が無くテスト未実行だった点も検収側で吸収
- [x] 2026-07-08 PR #5 マージ（gh api 直叩き）・ブランチ掃除
- [x] 2026-07-08 デプロイ: channel_secret を SSM SecureString 登録（Version 1）→ cdk deploy 成功（82秒、SettingsWebhook 一式 + PR #4 のアラート基盤 + worker 更新）→ 署名なし/偽署名 POST が本番で 403 になることを実証
- [x] 2026-07-08 LINE コンソール設定: Webhook URL 検証成功（コールドスタート約3秒で初回タイムアウト → ウォーム時に成功）。「Webhookの利用」ON 漏れで無反応事件のあと解決し、設定メニューの実機受信を確認。コールドスタート対策（メモリ増量等）は「実害が出たら」で見送り（てつてつ判断）
- [ ] SNS 購読確認メール（AWS Notifications）の Confirm をクリック（てつてつ手動・未確認）
- [ ] 翌朝配信の観測（7/9 朝7時〜）: ①1記事=1カード形式で届くか ②リージョン拡大/サイズ追加が消えているか（CloudWatch「Filtered as」ログと DynamoDB status=filtered で照合）③「いらない」タップ→「記録しました」返信が返るか ④トグル操作の返信が返るか（7/8 15:44 に reply の HTTPError×4 が未解明のまま。再送の期限切れ token 説。再発するなら reply エラーのステータスコードをログに出す改修を入れる）
- [ ] 設定メニューの文言改善の要否判断: 「ON リージョン拡大」では何のONか分からないとフィードバックあり。「🚫除外中: 〜」等への変更は配信カードを実際に見てから判断（観測駆動）

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
