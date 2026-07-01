# plan.md — aws-whatsnew-agent

## 1. 目的
AWS What's New（新機能・アップデート）を取得・要約し、LINE に届ける。
将来的にはエージェント的な振る舞い（対話的な深掘り、複数ソース横断、図解画像の自動生成など）を段階的に追加していく。

## 2. 段階（Phase）
### Phase 1（まず作る）: What's New を LINE に届ける
決定論的なパイプライン。LLM が自律的にツールを選ぶ「エージェント」要素は持たない。
- ① 取得: AWS What's New の公式 RSS フィードから直近の更新を取得
- ② 要約: Amazon Bedrock（Claude または Nova）で日本語要約
- ③ 配信: LINE Messaging API（Push または Broadcast）で送信
- ④ 実行: スケジュール実行（毎朝など）

### Phase 2（これから一緒に設計）: エージェント化
未確定。候補となる振る舞い:
- ユーザーの返信に応じて公式ドキュメントを自分で調べ、深掘りして返す
- 複数ソース（What's New + 公式 Doc + 料金）を横断して要約を組み立てる
- 要約から図解画像を自動生成して添付する（別ディレクトリの画像生成実験が原型）
- ※ Phase 2 の要件が固まった段階で Amazon Bedrock AgentCore の採用可否を判断する。

## 3. Phase 1 アーキテクチャ（案・確定は spec.md）
AWS / us-east-1 想定。
- EventBridge Scheduler → Lambda（Python 3.12）
- Lambda 内で: RSS 取得 → Bedrock 要約 → LINE Push
- シークレット: LINE トークン等は AWS 側（SSM Parameter Store SecureString または Secrets Manager）。ローカル開発は `~/.secrets/aws-whatsnew-agent.env`
- 代替案: GitHub Actions の cron（既存 daily-news-line-notifier と同じ手法）。AWS を使わず簡単だが、Bedrock 呼び出しの認証と実行環境を GitHub 側に持つ必要がある。

## 4. 設計上の重要決定
### 4.1 「AWS MCP を誰が叩くか」
- 開発時: Claude Code / Codex が AWS Knowledge MCP を叩いてドキュメント参照（開発支援。本番には含めない）。
- Phase 1 本番: MCP は使わない。What's New は RSS を直接取得、要約は Bedrock API を直接呼ぶ。
- Phase 2 本番: エージェントがツールを叩く構図。AgentCore を採用する場合は Gateway 経由で MCP ツールを接続できる。

## 5. 技術選定の理由（たたき台）
- RSS 直接取得: What's New は公式 RSS があり決定論的に取れる。スクレイピング不要。
- Bedrock: AWS 内で完結、モデル選択自由（Nova は agreement 不要で即利用可）。
- LINE Messaging API: 個人通知の実績あり。
- Phase 1 で AgentCore を使わない理由: タスクが決定論的でエージェント不要。導入は複雑さとコストを先食いするだけ。

## 6. 未決事項（要相談）
- 実行基盤: AWS (EventBridge + Lambda) か GitHub Actions か
- 要約モデル: Claude か Nova か
- 配信先: 自分個人（Push, USER_ID）か Broadcast か
- 送信頻度・時刻
- Phase 2 のエージェント要件（次の議論の主題）
