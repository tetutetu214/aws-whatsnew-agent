# spec.md — aws-whatsnew-agent（Phase 1）

（2026-07-06: plan.md 承認後の未決事項を確定して記述）

## 0. 確定した未決事項（plan.md §8 の回答）
- 送信件数: **上限なし（未送信の全件）**。ただし後述の初回シードと差分実行で暴発を防ぐ。
- 送信時刻: **毎朝 7:00（JST / Asia/Tokyo）**。
- フィルタ条件: **Phase 1 は絞らず全件対象**。関心サービスでの絞り込みは Nova 実測後に spec を改訂して追加（除外リストの口だけ用意しておく）。
- 状態ストア: **DynamoDB**。
- 要約モデル: **Amazon Nova で開始**。日本語品質が不足したら Claude に切り替え。
- IaC: **AWS CDK（Python 第一候補）**。

## 1. データ取得仕様
- ソース: AWS What's New 公式 RSS
  - URL: `https://aws.amazon.com/about-aws/whats-new/recent/feed/`
  - 取得は Lambda 内から標準ライブラリ `urllib` で HTTP GET。パースは依存を増やさないなら `xml.etree`、扱いやすさ優先なら `feedparser`。→ 実装時に決定。
- 記事の一意キー: RSS item の `guid`（無ければ `link`）。
- 取得範囲: RSS が返す直近分（通常 数十件）。この中から「DynamoDB に未記録のもの」だけを未送信として扱う。
- フィルタ: Phase 1 は全件通過。将来のために「除外サービス名リスト（空）」を設定値として持たせ、マッチしたら落とす口だけ用意する。

## 2. 状態管理（重複送信防止）
- テーブル名: `aws-whatsnew-agent-sent`（環境変数で上書き可）
- キー設計:
  - パーティションキー `article_id`（String） = guid または link
  - 属性: `link`, `title`, `published`（RSS の pubDate）, `sent_at`（送信成功時刻 ISO8601）, `status`（`sent` / `seeded`）
  - TTL 属性 `expire_at`（例: 90日）で古いレコードを自動削除しコストを抑える。
- 未送信判定: 取得した各記事の `article_id` を GetItem（またはバッチ）で確認し、未登録のものだけ要約・送信対象にする。
- 送信成功後に PutItem で `status=sent`, `sent_at` を記録。

### 2.1 初回シード（暴発防止）
- 初回デプロイ直後は RSS 全件が「未送信」に見えるため、そのまま動かすと数十件を一斉 Push してしまう。
- 対策: `SEED_MODE`（環境変数, 既定 false）を用意。true のとき、取得した記事を送信せず `status=seeded` で DynamoDB に記録するだけの「既読化」を行う。
- 運用: デプロイ直後に 1 回 `SEED_MODE=true` で手動実行 → 既存記事を既読化 → 以降 `SEED_MODE=false` の定期実行で「前回以降の新着」だけが送られる。

## 3. 要約仕様
- モデル: Amazon Nova（`amazon.nova-lite-v1:0` を第一候補。品質/コスト/レイテンシを実測して lite / pro を決定）。
- 呼び出し: Bedrock Runtime `Converse` API（`bedrock-runtime`）。
- 入力: 記事タイトル + RSS description（本文リンク先の読み込みは Phase 2）。
- 出力フォーマット（1記事あたり）: 日本語で1〜2行。「何が」「どう変わったか」を簡潔に。誇張・季節挨拶なし、事実ベース。
- トークン上限: 1記事あたり出力 max ~120 tokens 目安でコストを抑える。
- 失敗時: その記事の要約は「（要約失敗）タイトルそのまま」でフォールバックして送信を続行。フォールバック送信でも DynamoDB に記録する（重複防止優先）。

## 4. 配信仕様（LINE Messaging API）
- 方式: **Push**（自分の USER_ID 宛）。Broadcast は誤配信リスクのため不使用。
- メッセージ構造: 1通知 = ヘッダ行（日付・件数）＋ 記事ごとに「• 要約（1〜2行）\n  詳細: <link>」。
- 分割: LINE のテキストは1メッセージ最大 5000 文字、かつ Push は1リクエスト最大5メッセージ。件数が多い日は
  - 記事を N 件ずつのチャンクに分割し、複数メッセージ（最大5通/リクエスト）で送る。
  - それでも溢れる場合は複数回 Push する。
- 文字数・件数の実上限は実測で調整。まずは「1メッセージ ~10 記事、超えたら分割」を初期値にする。

## 5. インフラ / デプロイ
- IaC: **AWS CDK**。1スタックで Lambda / DynamoDB / EventBridge Scheduler / IAM ロール / SSM パラメータ参照を定義。CDK 言語は Python を第一候補（本プロジェクトが Python 主体のため）。
- 実行: EventBridge Scheduler → Lambda（Python 3.12）。
  - スケジュール: `cron(0 7 * * ? *)`、タイムゾーン `Asia/Tokyo`。
- Lambda 実行ロール（最小権限）:
  - `bedrock:InvokeModel`（対象 Nova モデル ARN に限定）
  - `dynamodb:GetItem` / `PutItem` / `BatchGetItem`（対象テーブルに限定）
  - `ssm:GetParameter`（LINE トークンのパラメータに限定, WithDecryption）
  - CloudWatch Logs 書き込み（基本ロール）
- シークレット:
  - LINE チャネルアクセストークン / 自分の USER_ID を **SSM Parameter Store SecureString** に格納。
  - パラメータ名（例）: `/whatsnew-agent/line/channel_token`, `/whatsnew-agent/line/user_id`
  - CDK コードにはトークン値を書かず、既に SSM に置いた SecureString を name 参照する（値はデプロイ前に手動 or CLI で put）。
  - ローカル開発は `~/.secrets/aws-whatsnew-agent.env`。リポジトリには `.env.example` のみ。
- リージョン: **us-east-1** を第一候補。使う Nova モデルの可用性を実装前に `aws bedrock list-foundation-models` で確認し、不可なら us-west-2 に切替。

## 6. エラーハンドリング / 監視
- 各ステップ（RSS取得 / 要約 / DynamoDB / LINE送信）の失敗はログに残す。
- 部分成功を許容: ある記事の送信に失敗しても他は続行。失敗した記事は DynamoDB に記録しないことで次回再試行（重複防止と両立）。
- LINE 送信の HTTP ステータスを確認。200 でも「友だち未追加 / チャネル不一致」で届かない罠があるため、初回は手動で受信確認する。
- CloudWatch Logs にトークン等シークレットを出さない。

## 7. Phase 1 の完了条件（再掲）
「毎日 7:00(JST) に、前回以降の未送信 What's New を日本語で短く要約して自分に LINE Push する。初回シードで暴発せず、重複送信しない。失敗はログに残る。」

## 8. 確定した残タスクの回答（2026-07-06）
- CDK 言語: **Python**（Lambda と統一）。
- LINE チャネル: **既存の line-notify 個人通知チャネルを流用**。トークン/USER_ID は `~/.secrets/line-notify.env`（正本）から取得し、SSM SecureString に登録して Lambda から参照する。connpass/duolingo と同じ LINE に混在する点は許容。
- 実装着手前に残るのは Nova モデルの us-east-1 可用性確認のみ（実測）。
