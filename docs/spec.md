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
  - `dynamodb:GetItem` / `PutItem`（対象テーブルに限定。BatchGetItem は未使用のため PR #1 で削除済み）
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

## 9. Phase 1.5: カテゴリフィルタ + LINE 設定・フィードバック（2026-07-08 追加、同日スコープ拡張）

§0「フィルタは Nova 実測後に spec を改訂して追加」の改訂。運用観測で「リージョン拡大」「インスタンスサイズ追加」の発表がノイズと判明。発表カテゴリでの除外に加え、**記事ごとの「いらない」フィードバック収集 → 集計 → カテゴリ育成**のループを LINE 内で完結させる。

### 9.1 カテゴリモデル（動的リスト）
- 保存先: SSM Parameter `/whatsnew-agent/filter/config`（String, JSON）。機密でないため SecureString にしない。配信 Lambda は実行のたびに読む（1日1回、コスト無視）。パラメータ未作成時はコード内の既定値で動作。
- 構造: `{"categories": [{"id", "label", "description", "enabled", "builtin"}]}` の配列。
- 既定カテゴリ（builtin=true、削除不可・enabled の OFF は可）:
  - `region_expansion`（リージョン拡大）: 既存サービス・機能の他リージョン展開。enabled=true
  - `instance_size`（インスタンスサイズ追加）: インスタンスタイプ / サイズの追加・拡大。enabled=true
- ユーザー定義カテゴリはトークから追加・削除できる（§9.5）。判定は `description` を LLM プロンプトに動的に埋め込んで行う。

### 9.2 フィルタ判定（ルール → LLM の二段構え）
1. **一段目（ルール）**: builtin カテゴリのみ定型句 regex リスト（コード内定数、タイトル対象）。例: `region_expansion` = `/available .*Regions?/i`, `/additional (AWS )?Regions?/i` など。ヒットしたらカテゴリ確定し LLM は呼ばない。2026-07-08 に直近 RSS 100 件で実測: region_expansion 15 件をルール確定・誤爆ゼロ（当初案の `/in .* regions?/i` は機能追加記事に誤爆したため available を必須化）。
2. **二段目（LLM）**: ルールで確定しなかった記事のみ、Nova Micro（`converse`, temperature=0, maxTokens 最小）に「enabled なカテゴリ一覧（id + description）+ `other`」から 1 語選ばせる。Judge 役なので出力の揺らぎを排除（enum 外の応答・API 失敗時は安全側 = `other` として配信。重要発表の取りこぼしをフィルタ誤動作より優先して防ぐ）。
- 判定の実行位置: 未送信判定（DynamoDB）の後・**要約の前**。除外記事の要約コストを払わない。
- 除外した記事は DynamoDB に `status=filtered` + `category` を記録し、翌日以降の再分類・再送信を防ぐ。
- 既存の `EXCLUDE_SERVICES`（未使用の文字列一致フィルタ）は本フィルタに置き換えて**廃止**する（設定手段の二重化を避ける）。

### 9.3 配信フォーマット変更（テキスト → 1 記事 = 1 カードの Flex Message）
- 配信の単位を「まとめテキスト」から **1 記事 = 1 Flex bubble（1 メッセージオブジェクト）** に変更。各カードに要約・詳細リンクボタン・「いらない」postback ボタンを持たせる。
- 全体設計との整合（2026-07-08 てつてつ提案で確定）: Phase 2 の説明画像自動生成は記事単位なので、記事をトーク上の独立したカードにしておけば bubble の hero 画像スロットに生成画像を差し込むだけで拡張できる。カテゴリフィルタで件数が絞られるからこそ 1 件ずつ送る形が成立する。
- 通数とコスト: Push は 1 リクエスト最大 5 メッセージオブジェクトなので 5 記事ずつバッチする。LINE の課金メッセージ通数は**宛先人数単位でカウントされ、1 リクエスト内のオブジェクト数は影響しない**（公式 Docs 確認済み 2026-07-08）。15 記事の日でも 3 通で、無料枠 200 通/月（connpass / duolingo と共有）に収まる。
- 既存 `MAX_ARTICLES_PER_MESSAGE`（テキスト分割用）は役割がなくなるため廃止し、API 上限の 5 記事/リクエストでバッチする。
- `altText`（通知プレビュー）は記事タイトルベース（形式は実装時に調整）。
- postback の `data` は 300 文字制限があるため article_id（URL 形式で長い）を直接入れない。送信時に **short_id（article_id の SHA-256 先頭 12 桁）** を採番して data に載せ、short_id → article_id の対応を同じ DynamoDB テーブルに `fb#<short_id>` キーの対応レコード（title / category 込み）として保存する。

### 9.4 フィードバック記録と集計
- 「いらない」タップ → webhook が short_id から記事を特定し、sent レコードに `feedback=dislike`, `feedback_at` を追記 → 「記録しました: <タイトル>」と返信。二度押しは上書き（冪等）。
- 集計（「集計」コマンド or 設定メニューのボタン）: テーブルを Scan し、いらない総数 / カテゴリ別内訳 / 直近のいらない記事タイトル（最新 10 件）を返信。
- データ窓: 既存 TTL 90 日をそのまま使う = 集計は直近 90 日の傾向。件数規模は 1 日数十件 × 90 日 ≈ 数千 item で Scan 許容。

### 9.5 LINE 設定操作（webhook）
- 新規 Lambda `SettingsWebhook` + **Lambda Function URL**（authType=NONE）。API Gateway は使わない（単一エンドポイント・低頻度に対して過剰、Function URL は追加コストゼロ）。
- セキュリティ: LINE Platform の署名 `X-Line-Signature` を channel secret で HMAC-SHA256 検証 + イベントの `source.userId` が登録済み USER_ID と一致するときだけ反応。channel secret は SSM SecureString `/whatsnew-agent/line/channel_secret` に追加登録。
- コマンド体系:
  - **「設定」** → カテゴリ一覧（enabled 状態付き）+ トグル postback ボタン + 「集計」「提案」「カテゴリ削除」「追加の使い方」ボタン
  - **トグル postback** → filter/config 更新 → 更新後の状態を返信
  - **「除外追加 <説明文>」** → Nova が説明文を `{id(slug), label, description}` に整形（Generator 役）→ config に enabled=true で追加 → 確認返信
  - **カテゴリ削除** → ユーザー定義カテゴリの一覧をボタン表示 → postback で削除（builtin は削除不可）
  - **「集計」** → §9.4 の集計を返信
  - **「提案」** → §9.6 の新カテゴリ提案
  - それ以外のメッセージには応答しない（共有チャネルのため誤爆防止）
- 返信は reply token を使う **Reply API**（Push と違い無料メッセージ数を消費しない）。
- IAM（webhook Lambda, 最小権限）: `ssm:GetParameter`（channel_secret / user_id / channel_token / filter/config。token は Reply API 送信に必要 = 2026-07-08 実装時に追加）、`ssm:PutParameter`（filter/config **のみ**）、`dynamodb:GetItem` / `UpdateItem` / `Scan`（対象テーブル限定）、`bedrock:InvokeModel`（Nova 限定。カテゴリ整形と §9.6 で使用）。
- webhook はイベント処理が失敗しても **200 を返す**（500 だと LINE が再送し、設定トグル等が二重適用されるため。失敗は CloudWatch ログに残す）。
- **共有チャネルの制約**: line-notify チャネルは connpass / duolingo と共有。webhook URL はチャネルに 1 つしか設定できないため、このチャネルの webhook はここが専有する。既存 2 つは Push 専用（webhook 不使用）なので影響なし。将来他プロジェクトが webhook を使いたくなったら、この Lambda をルーターにするかチャネル分離を検討。

### 9.6 新カテゴリの自動提案（学習ループ）
- 「提案」コマンド → 直近 90 日の `feedback=dislike` 記事タイトル群を Nova に渡し、**既存カテゴリでカバーされない共通パターン**を最大 3 件 `{label, description}` で提案させる（Generator 役、揺らぎ許容）。
- 各提案に「追加する」postback ボタンを付け、タップで config に追加 → 翌朝の配信から効く。**自動追加はしない**（人間の承認を必ず挟む）。
- フィードバックが 0 件のときは「まだデータがありません」と返す。

### 9.7 手動ステップ（てつてつ側の作業）
1. `aws login` 後、channel secret を SSM SecureString へ登録（値は `~/.secrets/line-notify.env` 正本から。画面には出さない）
2. `cdk deploy` 後、出力された Function URL を LINE Developers コンソールの Webhook URL に設定し「Webhookの利用」を ON
3. LINE で「設定」と送って動作確認

### 9.8 Phase 1.5 の完了条件
「配信が Flex 形式になり各記事に『いらない』ボタンが付く。タップが DynamoDB に記録され『集計』で内訳が見える。『設定』でカテゴリの ON/OFF・追加・削除ができ、除外 ON カテゴリの新着（ルールまたは Nova 分類で判定）は翌朝の配信から消え `status=filtered` で記録される。『提案』でいらないコーパスから新カテゴリ候補が返り、承認で追加できる。」

