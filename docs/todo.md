# todo.md — aws-whatsnew-agent

## Phase 1.5: カテゴリフィルタ + LINE 設定・フィードバック（2026-07-08 起票、同日「集計ループまで全部入り」でスコープ確定、spec.md §9）
- [x] スコープ確定: LINE 内で設定操作 / ルール+LLM 二段判定 / 「いらない」ボタンのみ / 集計・カテゴリ追加削除・LLM 提案まで全部入り（てつてつ回答済み）
- [x] 2026-07-08 実装（Codex gpt-5.5 委譲、11分で完了）: フィルタ二段判定 / 動的カテゴリ / EXCLUDE_SERVICES 廃止 / 配信 Flex 化（1記事=1カード）+ 「いらない」ボタン / SettingsWebhook Lambda + Function URL / CDK 更新 / テスト
- [x] 2026-07-08 検収（Fable レビューで 5 件修正）: ①regex `in .* regions` の誤爆を available 必須化で修正（実 RSS 100件で region 15件確定・誤爆ゼロを実測）②worker の不要な dynamodb:UpdateItem 削除 ③webhook 例外時も 200 返却（LINE 再送での二重適用防止）④Scan の 1MB ページネーション追加 ⑤除外記事のログ追加。pytest 60件パス / cdk synth 成功。Codex サンドボックスに pytest が無くテスト未実行だった点も検収側で吸収
- [x] 2026-07-08 PR #5 マージ（gh api 直叩き）・ブランチ掃除
- [x] 2026-07-08 デプロイ: channel_secret を SSM SecureString 登録（Version 1）→ cdk deploy 成功（82秒、SettingsWebhook 一式 + PR #4 のアラート基盤 + worker 更新）→ 署名なし/偽署名 POST が本番で 403 になることを実証
- [x] 2026-07-08 LINE コンソール設定: Webhook URL 検証成功（コールドスタート約3秒で初回タイムアウト → ウォーム時に成功）。「Webhookの利用」ON 漏れで無反応事件のあと解決し、設定メニューの実機受信を確認。コールドスタート対策（メモリ増量等）は「実害が出たら」で見送り（てつてつ判断）
- [ ] SNS 購読確認メール（AWS Notifications）の Confirm をクリック（てつてつ手動・未確認）
- [x] 2026-07-08 16:30 初実戦（てつてつ提案で手動 invoke を前倒し）: 朝7時以降の自然新着 8 件に対し sent=5 / filtered=3。除外3件は全て region_expansion で誤爆ゼロ（S3 Vectors GovCloud / Redshift RG GovCloud / S3 Express One Zone Frankfurt）。カード配信も到達
- [x] 2026-07-08 LINE チャネル専用化: AWS WhatsNew チャネル新設（てつてつ）→ SSM token/secret 差し替え（Version 2、正本 ~/.secrets/aws-whatsnew-line.env）→ 新チャネルで疎通 push・新 secret 署名 200 確認 → webhook を新チャネルへ移設・旧チャネル OFF。旧トークの配信済みカードのボタンは無効化（knowledge.md 参照）
- [x] 2026-07-08 ボタン文言変更（PR #6）: 「いらない」→「Not for Me」（サービス否定に読める問題）。集計表示も追随。pytest 60件パス → deploy → 今日の5件を新トークに再送済み
- [x] 2026-07-08 17:12 フィードバック経路の実機確認: 新チャネルの webhook 設定後、RDS for Oracle 記事への Not for Me タップが webhook 着信（1.0秒・エラーなし）→ DynamoDB feedback=dislike 記録 → 「記録しました」返信まで全通。15:44 の reply HTTPError×4 は「チャネル切り替え期の期限切れ token による一過性」で確定（新チャネルの新規イベントでは再発せず）
- [ ] 実機の残り観測: ①「集計」で Not for Me 総数:1 と RDS 記事が出るか ②設定メニューのトグル操作 ③7/9 朝7時の定期実行が新チャネルに届くか ④「提案」はフィードバックが数件貯まってから
- [ ] SNS 購読確認メール（AWS Notifications）の Confirm クリック（てつてつ手動・まだなら）
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

## Phase 2: 図解の自動生成エージェント（2026-07-09 着手・設計確定）
設計根拠は plan.md「Phase 2」/ spec.md §10。構成: LINE「グラフィカル解説」ボタン → webhook 即200＋「生成中」reply → AgentCore Runtime 非同期起動 → 記事取得→(AWS MCP)→Bedrock OpenAIモデルで自己完結HTML生成→S3→presigned URL→LINE Push で「📊 図解を開く」リンク。全 IAM・外部キーゼロ。画像エンジンは案C（GPT-5.5がHTMLを書く。原型 aws-whatnew-visual/html_test/ で実証済）。

- [x] 2026-07-09 設計: plan.md Phase 2 実体化 / spec.md §10 追記
- [x] 2026-07-09 実装（2.1+2.2）: Flexにボタン追加 / webhook explain分岐＋非同期trigger(agent_trigger.py) / explainer.py（記事→HTML→S3→presigned→Push）/ feedback mapping に description・link 追加 / AgentCore Runtime成果物(agent/agent_runtime.py・Dockerfile・requirements) / CDK(S3・実行ロール・InvokeAgentRuntime権限)
- [x] 2026-07-09 ローカル検収＋レビュー反映: reviewer 監査で blocking 1件（invoke_agent_runtime が同期でwebhookをブロック）を検出 → **webhook→dispatcher Lambda(Event)→AgentCore の2段非同期**に修正。例外スコープ・テスト強化も反映。pytest 78件パス / cdk synth 成功。デプロイ前の要確認5点は spec.md §10.10
- [x] 2026-07-10 方針変更（AgentCore→C案）: AgentCore starter-toolkit が非推奨化していたため、てつてつ判断で **v1 は AgentCore を挟まず dispatcher Lambda が直接 generate_explainer を実行**する構成に変更（AgentCore は将来 MCP 深掘りが要る段で。agent/ に成果物は残置）
- [x] 2026-07-10 本番デプロイ＆バックエンドE2E成功: `cdk deploy` 済（ExplainerBucket・ExplainerDispatcher・ExplainerViewer + Function URL）。dispatcher 直接 invoke で status=sent、viewer URL(85字) が HTTP200/text/html で図解を返し LINE Push まで到達。gpt-oss-120b は us-east-1・IAM のみで動作（推論プロファイル不要を実証）
- [x] 2026-07-10 presigned URL 罠を解消: presigned は1682字で **LINE の URI ボタン上限(1000字)超過→400**。私有S3のまま **閲覧Lambda(Function URL)** が短いURL(`.../?id=<short_id>`)で配る方式に変更（公開バケットは作らない＝てつてつ判断B）
- [ ] **実機ボタンテスト**: 既存カードにボタンが無いので、次の朝7時配信 or 手動再送のカードで「グラフィカル解説」タップ→Push を確認
- [ ] 品質改善: ①description 付きカードで richに（実装済・新着から効く）②必要なら `EXPLAINER_MODEL_ID`/`EXPLAINER_BEDROCK_REGION` を GPT-5.5(us-east-2)へ ③HTML下端はみ出し等プロンプト調整
- [x] 2026-07-11 **本来の AgentCore + MCP 構成を本番デプロイ・E2E成功**（whatsnewExpl/, commit cbe0346）: `agentcore create`→main.py に explainer/aws_mcp 移植→cdk-stack.ts に実行ロールIAM+env追記→`agentcore deploy`(サーバレス/CodeZip)成功。Runtime ARN=`arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/whatsnewExpl_whatsnewExplainer-9WFmoq38Ne`。invoke_agent_runtime で status=sent、MCP由来のAPI事実(BatchWriteRecord/Iceberg/Lake Formation)が図に反映を実証
- [x] 2026-07-11 **残1完了: ボタン→AgentCore の配線**（commit ec3e151）: dispatcher を invoke_agent_runtime へ戻し AGENT_RUNTIME_ARN env＋InvokeAgentRuntime 権限を付与→ cdk deploy 済。dispatcher 直接 invoke で dispatcher→AgentCore→図解→LINE Push を実証。ボタン付きテストカードも送信済（実機タップ確認待ち）
- [x] 2026-07-11 **残2完了: HTMLレイアウト安定化**（commit ec3e151）: HTML_SYSTEM_PROMPT を強化（.canvas overflow:hidden/flex-column、position:absolute 禁止、要素数を枠に収める）→ agentcore deploy 再→本番で崩れ解消・3カード＋4バッジがきれいに収まるのを確認
- [ ] **実機ボタンタップの最終確認**（てつてつ）: 送信済テストカードの「グラフィカル解説」を押し、数十秒後に図解が届くのを確認。以降の新着カードにも自動でボタンが付く
- [ ] 品質のさらなる向上（任意）: GPT-5.5(us-east-2)への切替、下部の余白調整、AWS MCP の read_documentation 併用でさらに深い情報
- [x] 2026-07-11 検証・実装（AgentCore移行の地ならし）: AgentCore が serverless/CodeZip と実証・雛形生成確認 / AWS Knowledge MCP を自前コードから実データ取得成功(base URL) / MCP富化で図が正確化するのを実証 / `src/aws_mcp.py`+テスト4件
