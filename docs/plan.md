# plan.md — aws-whatsnew-agent

（2026-07-01: Codex クロスレビュー20項目を反映して改訂）

## 1. 目的
AWS What's New（新機能・アップデート）を取得・要約し、LINE に届ける。将来的にエージェント的な振る舞い（対話的な深掘り、複数ソース横断、図解画像の自動生成）を段階的に追加する。

## 2. 段階（Phase）
### Phase 1: What's New を LINE に届ける（決定論パイプライン）
LLM が自律的にツールを選ぶ「エージェント」要素は持たない。
- ① 取得: What's New 公式 RSS から直近の更新を取得
- ② フィルタ: 関心サービス／重要度でルールベースに絞る（全件は送らない）
- ③ 要約: Amazon Bedrock で日本語要約
- ④ 配信: LINE Messaging API（Push, 自分の USER_ID）
- ⑤ 状態管理: 送信済み記事を記録し重複送信を防ぐ
- ⑥ 実行: EventBridge Scheduler で毎朝

#### Phase 1 の完了条件（Definition of Done）
「毎日指定時刻に、未送信の What's New を最大 N 件取得し、日本語で短く要約して自分に LINE Push する。重複送信しない。失敗はログに残る。」

### Phase 2（これから一緒に設計）: エージェント化
未確定。候補: 返信に応じて公式 Doc を深掘り／複数ソース横断／図解画像の自動生成（別ディレクトリの画像生成実験が原型）。
- 要件が固まった段階で、オーケストレーション方式（Lambda + Bedrock Converse / Step Functions / AgentCore 等）を比較して決める。**AgentCore は候補の一つに留める**（採用条件は要件確定後に定義）。

## 3. Phase 1 アーキテクチャ（確定方針・詳細は spec.md）
実行基盤: **AWS（EventBridge Scheduler + Lambda, Python 3.12）** に決定。
理由: 将来の LINE Webhook 受信やエージェント化への接続を AWS 内で自然につなげられる。学習面でも AWS 上に置く。「毎朝送るだけ」には過剰との指摘（Codex）は承知の上で、拡張性を優先する判断。
- EventBridge Scheduler → Lambda
- Lambda 内: RSS 取得 → フィルタ → Bedrock 要約 → 状態確認 → LINE Push
- 状態ストア: 送信済み記事の id/link/published を DynamoDB（または S3）に保存
- 代替案（不採用）: GitHub Actions cron。最短だが将来の受信・拡張が AWS 外になるため今回は採らない。

## 4. 設計上の重要決定
### 4.1 「AWS MCP を誰が叩くか」
- 開発時: Claude Code / Codex が AWS Knowledge MCP を叩く（開発支援。本番に含めない）。
- Phase 1 本番: MCP は使わない。RSS 直接取得、Bedrock API 直接呼び出し。
- Phase 2 本番: エージェントがツールを叩く。ただし「本番ユーザー応答で使うツール接続」と「開発時に Codex/Claude が使う MCP」は、認証・権限・コスト・監査が別物として扱う。

### 4.2 状態管理（重複送信防止）
送信済み記事を DynamoDB に記録（キー: 記事 link または guid）。取得時に未送信のみ抽出。再実行・取りこぼしに耐える。

### 4.3 シークレット / 認証
- Lambda は IAM 実行ロールで Bedrock / DynamoDB にアクセス（長期キー不要）。
- LINE トークンは SSM Parameter Store SecureString（または Secrets Manager）。
- ローカル開発は `~/.secrets/aws-whatsnew-agent.env`。リポジトリには `.env.example` のみ。ログにトークンを出さない。

## 5. 技術選定の理由
- RSS 直接取得: What's New は公式 RSS があり決定論的に取れる。スクレイピング不要。
- Bedrock 要約モデル: **Nova で開始**（低コスト・agreement 不要※）、品質不足なら Claude に切り替え。比較軸 = 日本語品質 / コスト / レイテンシ / コンテキスト長 / リージョン可用性 / 出力安定性。
  - ※ モデルの利用条件・リージョン可用性は変わり得るので spec 作成時に AWS 側で確認する（本 plan の断定は 2026-07-01 時点）。
- リージョン: us-east-1 想定。ただし使う Bedrock モデルの可用性次第で us-west-2 を検討（spec で確認）。
- LINE Messaging API: 個人通知の実績あり。Push + 自分の USER_ID。Broadcast は誤配信リスクがあり使わない。

## 6. 配信フォーマット（方針）
- LINE は長文に弱い。1 回の通知で「上位 N 件」、1 記事 = 1〜2 行の要約 + 詳細リンク。
- 深い変更内容はリンク先を読まないと不足するが、Phase 1 は RSS 項目のみで要約。リンク先本文の読み込みは Phase 2。

## 7. コスト・運用
- コスト要因: Bedrock 要約 / Lambda / EventBridge / DynamoDB / SSM。Phase 1 は「1 日最大 N 件・1 記事あたり最大 M トークン」で上限を意識。
- 障害時: RSS 取得失敗・Bedrock 失敗・LINE 送信失敗をログに残す。部分成功を許容し、失敗記事は未送信のまま次回再試行（重複防止と両立）。

## 8. 未決事項（spec で詰める）
- N（1 日の最大件数）、送信時刻
- 関心サービス／除外サービスのフィルタ条件
- 状態ストア: DynamoDB か S3 か
- 要約モデルの最終決定（Nova 実測後）
- Phase 2 のエージェント要件（次の議論の主題）
