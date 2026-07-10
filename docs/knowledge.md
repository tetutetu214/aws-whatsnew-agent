# knowledge.md — aws-whatsnew-agent

## 決定事項
- 2026-07-11: **図解モデルを Claude Sonnet 4.6 に決定**（gpt-oss は情報量が薄く役に立たない・英語混在とてつてつ指摘）。**GPT-5.5 はこのアカウントの Bedrock に未提供**（全リージョン gpt-oss 系のみ、`openai.gpt-5.5-*` は invalid）。図解の密度・品質は Claude が突出。`us.anthropic.claude-sonnet-4-6`（us-east-1 推論プロファイル、IAM は inference-profile ＋ 各リージョン foundation-model の両 ARN が要る）。品質は参考画像（ChatGPT製）と同等：ヘッダー＋特徴6＋動作フロー＋アーキ図＋API比較表＋利用シーン/主な機能/メリット。
- 2026-07-11: **HTML は縦に伸ばす前提でプロンプトを組む**（PNGと違い1画面に収める必要がない）。「1画面に収める・要素削る」制約が薄さの主因だった。密度重視・多セクション・日本語固定に刷新。maxTokens 4000→16000（密な図が途中で切れないように）。
- 2026-07-11: **Claude 密生成は約165秒 → read_timeout 対策が必須**。既定 read_timeout(60s) だとタイムアウト→botocore リトライで多重生成＆失敗（CloudWatch で `ReadTimeoutError on .../claude-sonnet-4-6/converse`、308秒で error を確定）。explainer の bedrock-runtime に read_timeout=300、**dispatcher の bedrock-agentcore クライアントにも read_timeout=290**（AgentCore の完了を待つため）、両方 retries=1。dispatcher Lambda timeout=300s 内に収まる。
- 2026-07-11: **本来の AgentCore + MCP 構成に戻す**（Lambda v1 は非推奨警告に引きずられた縮小版だったとてつてつが指摘）。検証済み事実を docs/agentcore-plan.md に集約。要点: **AgentCore Runtime はサーバレス・ビルド既定 CodeZip（Docker/ECR 不要）**＝「コンテナ必須/重い」は私の誤り。正式 CLI は npm の `@aws/agentcore`（`agentcore create`→`deploy`、CDKベース）。雛形は Strands+MCPクライアント込み。
- 2026-07-11: **AWS Knowledge MCP は自前コードから直接叩ける**（認証不要）。エンドポイントは **ベース URL `https://knowledge-mcp.global.api.aws`**。**`/mcp` を付けると tool-call が「Http operation is not supported for gateway protocol type MCP」で 400**（initialize/tools-list は通るが call が落ちる罠）。ツール `aws___search_documentation`(search_phrase必須)/`aws___read_documentation`(requests:[{url}])。実装 src/aws_mcp.py（公式mcpクライアント・遅延import・runner注入でテスト、pytest 4件）。
- 2026-07-11: **MCP 富化の効果を実証**。SageMaker Feature Store で薄い図の埋め草が MCP 由来の API 事実（BatchWriteRecord/list_records/TTL自動削除/TargetStores）に置換され正確化。MCP 富化は **依存管理のある AgentCore CodeZip 側に置く**（stdlibのみの現行Lambda from_asset("src")には mcp 同梱不可のため。MCP は AgentCore 移行とセット）。
- 2026-07-10: **本番稼働開始（バックエンドE2E成功）**。方針を AgentCore→C案に変更: AgentCore の starter-toolkit CLI が非推奨化（新CLIは @aws/agentcore）していたため、てつてつ判断で **v1 は AgentCore を挟まず dispatcher Lambda が直接 explainer.generate_explainer を実行**。AgentCore は将来 MCP 深掘りが要る段で載せる（agent/ に成果物残置）。gpt-oss-120b は **us-east-1・IAM のみで動作**（bedrock:InvokeModel の foundation-model/openai.* で通る＝推論プロファイル不要を実証）。dispatcher 直接 invoke で status=sent を確認。
- 2026-07-10: **presigned URL は LINE で使えない**。presigned は SigV4 で1682字になり **LINE の URI ボタン上限(1000字)を超えて 400 Bad Request**。→ 私有 S3 のまま **閲覧 Lambda(Function URL)** を1個立て、`GET /?id=<short_id>` で私有オブジェクトを text/html で返す短いURL(85字)で配る方式に変更（公開バケットは作らない＝てつてつ判断B。id は `[0-9a-f]{1,64}` 限定でキーinjection防止）。plan/spec の「presigned で配る」記述はこれで置換。
- 2026-07-10: gpt-oss-120b の図解は動作するが原型(gpt-5.5)より簡素。入力が title だけだと内容が薄く一部一般化される。→ feedback mapping に description を保存し新着カードから richに。GPT-5.5(us-east-2)へは EXPLAINER_MODEL_ID/REGION の env 差し替えで切替可。
- 2026-07-09: Phase2（図解生成エージェント）の設計を確定し 2.1/2.2 を実装。画像生成エンジンは3案比較の結果 **案C=GPT-5.5 が自己完結HTMLを書き、ブラウザ表示に委ねる**方式を採用。理由: Bedrock 上の OpenAI モデルは公式に text-in/text-out のみ（画像不可）だが SVG/HTML はテキストなので生成でき、**全 IAM・外部キーゼロ・日本語確実**。A案(gpt-image直叩き)は Bedrock 非対応で OpenAI キーが要るため不採用、B案(Nova Canvas等拡散モデル)は日本語インフォグラフィック文字が崩れやすく不採用。原型 `~/projects/aws-whatnew-visual/html_test/` で codex(gpt-5.5)→自己完結HTML→Chrome描画の実測で有効性を確認（日本語崩れなし。下端はみ出しは要調整）。
- 2026-07-09: 配信は **HTML を S3 に置き presigned URL リンクを LINE Push**（PNG化しない）。理由: LINE 画像インライン表示のためだけに PNG 化するのは本末転倒。HTML はズーム可・レスポンシブ・文字鮮明でスマホで密な日本語図解を読むのに固定PNGより優れ、描画工程(Chrome/AgentCore Browser)も不要で堅牢・安価。インライン表示が要るとき初めてPNG化を足す。
- 2026-07-09: OpenAI モデルは 2026-06-01 に **Bedrock ネイティブ GA**（GPT-5.5/5.4/Codex）。`bedrock:InvokeModel` を IAM で叩くだけで呼べ、OpenAI キー不要。ただし**画像生成は非対応**（gpt-image は OpenAI ホスト側のみ）。GPT-5.5 は **US East (Ohio, us-east-2)**、本スタックは us-east-1 なので図解の Bedrock 呼び出しだけリージョンを分ける(`EXPLAINER_BEDROCK_REGION`)。既定モデルは確実に存在する `openai.gpt-oss-120b-1:0`(us-east-1) にしておき、GPT-5.5 へは env で切替。
- 2026-07-09: 図解生成は数十秒かかるため非同期。webhook は即200＋「生成中」reply→完了後 **reply ではなく Push**（reply トークンは短命なため）。**重要**: `invoke_agent_runtime` は同期APIなので webhook(60s) から直叩きするとブロック→タイムアウト→LINE再送→二重生成になる（reviewerが検出）。対策として **webhook → dispatcher Lambda(InvocationType=Event で投げっぱなし) → AgentCore Runtime** の2段構えにした。dispatcher は webhook のクリティカルパス外なので timeout 300s で AgentCore 完了まで待ってよい。AgentCore Runtime は CFn ではなく `agentcore configure/launch`（Docker）でデプロイし、CDK は S3・IAM・dispatcher・権限のみ担当。デプロイ前の要確認（推論プロファイル要否・InvokeAgentRuntimeのARN形・presigned失効・冪等性）は spec.md §10.10。
- 2026-07-01: プロジェクト名を aws-whatsnew-agent に決定。GitHub Private で作成。
- 2026-07-01: Phase を分割。Phase1 = 決定論パイプライン（LINE 送信）、Phase2 = エージェント化（未設計）。
- 2026-07-01: MCP は開発時のみ使用。Phase1 本番には組み込まない（RSS / Bedrock を直接呼ぶ）。
- 2026-07-01: Phase1 実行基盤を AWS（EventBridge Scheduler + Lambda）に確定。「毎朝送るだけには過剰」との Codex 指摘は承知の上で、将来の Webhook 受信・エージェント化への接続と学習を優先。
- 2026-07-01: 要約モデルは Nova で開始し、品質不足なら Claude に切り替える方針。
- 2026-07-01: Codex クロスレビュー（20項目）を plan.md に反映。主な追加=状態管理（重複送信防止）、Phase1完了条件、配信フォーマット（上位N件・LINE長文対策）、AgentCore はトーンダウンして候補扱い。
- 2026-07-06: plan.md の未決事項を確定し spec.md を作成。決定=送信は上限なし全件/毎朝7時JST/フィルタは Nova 実測後に追加（初期は全件通過）/状態ストアは DynamoDB/要約は Nova(nova-lite 第一候補)で開始/IaC は CDK(Python 第一候補)。
- 2026-07-06: 「全件・フィルタ後回し」だと初回に過去記事を一斉 Push する暴発リスクがあるため、SEED_MODE(既定false) を導入。初回だけ true で既読化(status=seeded)し送らない、以降は差分のみ送る設計にした。
- 2026-07-06: CDK 言語は Python に確定（Lambda と統一）。LINE は既存の line-notify 個人通知チャネルを流用（正本 ~/.secrets/line-notify.env → SSM SecureString へ登録して Lambda 参照）。connpass/duolingo と同じ LINE に混在するのは許容。
- 2026-07-08: Phase 1.5 のスコープを確定（spec.md §9）。設定画面は Web でなく LINE 内完結（署名検証 + userId 照合の webhook）、フィルタはルール→Nova 分類の二段構え、カテゴリは SSM 上の動的リスト、「いらない」フィードバック収集 → 集計 → LLM 新カテゴリ提案（人間承認制）の学習ループまで全部入り。
- 2026-07-08: 配信単位を「まとめ」から 1 記事 = 1 Flex カードに変更（てつてつ提案）。Phase 2 の記事ごと説明画像生成に hero 画像スロットで直結する器。LINE の課金通数は宛先人数単位で 1 リクエスト内のメッセージオブジェクト数（最大5）は不算入と公式 Docs で確認済みのため、5 記事/リクエストのバッチで無料枠 200 通/月に収まる。

- 2026-07-08: フィードバックボタンの文言は「いらない」→「Not for Me」（てつてつ指定）。「いらない」はサービス自体の否定に読めて気分が悪い、「自分には関係ない」の意を明示する。ユーザー向け文言はこのニュアンスに注意。
- 2026-07-08: LINE チャネルを専用化（AWS WhatsNew チャネル新設・同一プロバイダー配下）。token/secret の正本は `~/.secrets/aws-whatsnew-line.env`、SSM の既存パラメータ名に値だけ差し替え（Version 2）。userId はプロバイダー共通なので変更なし。旧 line-notify チャネルの webhook は OFF。**切り替え前に旧トークへ配信済みのカードのボタンは、旧チャネル経由でイベントが飛ぶため全て無効**（押しても何も起きない）。

## 学習済み概念（理解度テスト正解済み・次回スキップ可）
- 2026-07-08: webhook 署名検証 = HTTPS が守るのは「通信の途中」、署名が守るのは「送信者が本物か」。channel secret を鍵にした本文 HMAC-SHA256（X-Line-Signature）は secret を知らない第三者には偽造できないため、Function URL が authType=NONE でも偽リクエストを弾ける。
- 2026-07-08: SSM 動的設定 vs 環境変数 = 環境変数は関数定義の一部なので変更にデプロイ相当の関数更新が要る。SSM なら実行時に読むため PutParameter した瞬間に反映され、複数 Lambda で同じ設定を共有できる。Standard パラメータは保存も標準 API も無料（Advanced のみ月 $0.05/個）。
- 2026-07-08: LLM の Judge / Generator 分担 = 分類（Judge）は同じ入力に同じ判定を返す再現性が信頼の源で temperature=0。提案（Generator）は発想の幅が価値なので揺らぎ許容。
- 2026-07-08: webhook の 200 固定 = 500 を返すと LINE が再送し、トグルのような非冪等操作が二重適用される。失敗はログに残して監査。
- 2026-07-08: DynamoDB Scan の 1MB 打ち切り = エラーにならず途中まで返る（LastEvaluatedKey が付くだけ）。全件集計はループ必須。
- 2026-07-08: 公開 Function URL の安全性は「URL を LINE に設定したかどうか」と無関係 = 署名検証がある限り設定前後で危険度は変わらない。webhook 誤動作時の最速の止め方は AWS を触らず LINE 側の「Webhookの利用」を OFF（配信 Lambda に影響しない）。
- 2026-07-04: IAM ロールの分離 = 「呼ぶ側」と「呼ばれる側」は別主体。Scheduler が Lambda を起動する権限は scheduler.amazonaws.com が assume する専用ロールに持たせる（Lambda 実行ロールとは別物）。
- 2026-07-04: SecureString の復号 = AWS 管理キー（aws/ssm）はキーポリシーが SSM 経由の利用をアカウント内に許可済みのため、呼び出し側は ssm:GetParameter だけでよい。カスタマー管理キーなら kms:Decrypt が必要。
- 2026-07-04: 本スタックの固定費 = ほぼゼロ（DynamoDB オンデマンド/Lambda/Scheduler 無料枠/SSM Standard すべて従量・無料。課金は Bedrock 要約の従量分のみ）。
- 2026-07-06: CDK の本質 = Python コードを CloudFormation テンプレートに synth して deploy する（プログラミング言語で IaC を書ける）。
- 2026-07-06: DynamoDB 冪等 + SEED_MODE の目的 = 何度実行しても二重送信せず、初回の過去記事一斉送信も防ぐ。
- 2026-07-06: Bedrock ON_DEMAND を選ぶ理由 = モデルID を直接呼べ、INFERENCE_PROFILE 必須モデルのようなクロスリージョン推論プロファイル ARN の事前作成が不要。
- 2026-07-06: DynamoDB スキーマレス = テーブル定義が強制するのはパーティションキー（+ソートキー）のみで、属性追加に ALTER TABLE 相当は不要。put_item は「アイテム全体の置き換え」（マージではない。部分更新は update_item）。属性の有無が混在するレコードは読む側が「属性なし」に備えれば共存できる（旧レコードの一括更新は不要）。
- 2026-07-06: デプロイ3軸（PR #3）= Lambda コードのみの変更なら cdk deploy で更新されるのは Lambda だけ（テーブル/Scheduler/IAM は不変）。DynamoDB オンデマンドの書き込み課金は 1KB 単位のリクエスト数なので短い属性追加はコスト不変。ロールバックは前コミットで再デプロイ（保存済みの余分な属性は無害で TTL で消える）。

## 実測メモ
- 2026-07-06: Nova Micro 要約の初サンプル1件（GameLift DDoS SDK 記事）: 内容は正確だが「〜なりました。」と「〜させる。」の敬体/常体混在、指定1〜2行に対し2文でやや長め。判定は実配信数日分で行う（summary が DynamoDB に貯まる）。
- 2026-07-06: us-east-1 の Nova 可用性を確認。`amazon.nova-lite-v1:0` と `amazon.nova-micro-v1:0` は ON_DEMAND 対応（推論プロファイル不要で Converse 直呼び出し可）。`amazon.nova-2-lite-v1:0` は INFERENCE_PROFILE 必須。短い日本語要約なので Nova Micro を第一候補、品質不足なら Lite に上げる。

## 知見 / ハマり
- 2026-07-08: **フィルタ regex の `\bin .* regions?\b` は機能追加記事に誤爆する**。「... on 26 additional EC2 instance types in all commercial regions」のような記事が region_expansion 扱いになり、除外はユーザーに見えないため無音で欠落する。展開表現（available 等）を必須にして解決。除外記事は CloudWatch ログに必ず残す（誤爆の監査経路）。
- 2026-07-08: **LINE webhook は失敗時も 200 を返す**。500 を返すと LINE Platform が再送し、設定トグルのような非冪等操作が二重適用される。イベント単位で例外を捕捉しログへ。
- 2026-07-08: **DynamoDB Scan は 1MB で打ち切られる**。集計用の全件 Scan は LastEvaluatedKey ループ必須（sent レコードは summary 込みで 1 件 ~1KB、90 日分で 1MB を超えうる）。
- 2026-07-08: **Codex サンドボックスには pytest が無い**。「py_compile と import 確認のみ」の報告を「テスト済み」と読み違えない。検収側での pytest 実行が必須（今回 60 件は全て検収側で初実行）。
- 2026-07-08: Codex バックグラウンドタスクの完了確認は `codex-companion.mjs status <task-id>` の直叩きが確実（監視サブエージェントのポーリング委譲は完了検知に失敗して 50 分空回りした）。
- 2026-07-04: **SSM パラメータ名は `aws` / `ssm` で始まる名前が予約されていて登録不可**（AccessDeniedException: No access to reserved parameter name）。プロジェクト名が aws- で始まる場合はそのままパラメータ名に使えない。`/aws-whatsnew-agent/...` → `/whatsnew-agent/...` に変更（PR #2）。
- 2026-07-04: `aws lambda update-function-configuration --environment` は**環境変数の全置換**（マージではない）。既存の全変数を含む `{"Variables": {...}}` 形式の JSON を渡す。get-function-configuration で取得した Variables マップをそのまま渡すとラッパー不足で ParamValidation エラー。
- 2026-07-04: 疎通確認の手法 = 全件既読の状態で DynamoDB から1件 delete-item → 本番モードで invoke すると「人工新着1件」で要約→LINE Push の全経路を検証できる。レコードは送信成功時に mark_sent で自動再作成されるため後始末不要。
- 2026-07-04: CDKToolkit スタックが UPDATE_ROLLBACK_COMPLETE でも bootstrap version 25 が生きていれば cdk deploy は正常に動く（再 bootstrap 不要だった）。
- 2026-07-04: PR #1 の Fable レビューで検出・修正した4件。①`astimezone()` 引数なしは実行環境のローカルTZ に変換されるため、Lambda(UTC) では朝7時JST実行時にヘッダーが前日日付になる → JST 固定オフセット(+9)で修正（JST は夏時間なし、tzdata 依存も回避）。②Lambda タイムアウト60秒は記事滞留日（re:Invent 期等）に直列 Bedrock 要約が超過→全滅→翌日も全滅のループリスク → 300秒に引き上げ。③未使用 `dynamodb:BatchGetItem` 権限を削除。④Bedrock ARN の us-east-1 ハードコードを self.region に統一。
- 2026-07-04: snap 版 gh は `gh pr merge` 不可のため `gh api repos/.../pulls/1/merge -X PUT -f merge_method=merge` でマージ（既知の回避策）。
- 2026-07-06: What's New RSS は1回で100件返る。SEED_MODE 無しの初回実行だと100件を要約＆Push してしまうため、初回 SEED_MODE=true の既読化が必須と実測で裏付け。
- 2026-07-06: RSS の description は `<p>` 等の HTML タグ入り。要約入力を汚さないよう rss.py でタグ除去＋エンティティ復号＋空白整形を実施。
- 2026-07-06: `python app.py` を CDK CLI 無しで直接叩くと cdk.out が出ない（標準出力先が temp になる）。synth 検証は `cdk synth`、または App(outdir='cdk.out') を明示して呼ぶ。
- 2026-07-06: Bedrock Converse API の呼び出し権限は `bedrock:InvokeModel`。ON_DEMAND 基盤モデルの ARN はアカウント無し（`arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-*`）。

- Codex CLI 0.130.0 は画像生成に対応（`codex features list` に image_generation stable）。
  - コマンド: `codex exec --model gpt-5.5 --sandbox workspace-write --skip-git-repo-check "..." < /dev/null`
  - 画像は `~/.codex/generated_images/<uuid>/` に出力。日本語文字も崩れず描画できた実績あり。
  - 画像生成実験（gen_image.sh）は別ディレクトリ `~/projects/aws-whatnew-visual/` にある。Phase2 の図解自動生成の原型になり得る。

## 参考（既存プロジェクト）
- daily-news-line-notifier: HuggingFace 論文を GitHub Actions cron で LINE Push。骨格を流用可能。
- 20250915_get_awsnews: What's New RSS → Bedrock 要約の PoC（4ブロック要約）。
