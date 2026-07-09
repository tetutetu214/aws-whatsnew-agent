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

### Phase 1.5: カテゴリフィルタ + LINE 設定・フィードバック（2026-07-08 追加）
運用観測の結果「リージョン拡大」「インスタンスサイズ追加」の発表はノイズと判明。発表の**種類（カテゴリ）**で除外するフィルタに加え、記事ごとの「いらない」フィードバックを収集・集計し、除外カテゴリを育てるループを LINE 内で完結させる（詳細は spec.md §9）。
- フィルタ判定: **ルール（定型句 regex）→ LLM（Nova Micro 分類）の二段構え**。定型句で確定できる記事は LLM を呼ばず、曖昧な記事だけ分類にかける。
- カテゴリは固定 enum ではなく **SSM 上の動的リスト**。トークから追加・削除でき、「いらない」投票のコーパスから LLM が新カテゴリ候補を提案する（追加は人間承認制）。
- 設定画面: **LINE 内で完結**（「設定」送信 → トグルボタン → postback で SSM 更新）。配信は Flex Message 化して各記事に「いらない」ボタンを付ける。Web UI・新規ホスティング・新規認証を増やさない。
- 配信単位は「まとめ」ではなく **1 記事 = 1 カード**（てつてつ提案）。Phase 2 の記事ごと説明画像生成にそのまま接続する器であり、フィルタで件数が絞られるから成立する。通数は宛先単位カウントのため 5 記事/リクエストのバッチで無料枠内。
- 選定理由: 通知の受け口が LINE なので「いらない通知を見たその場で押せる」導線が自然。Web 画面案（Cloudflare Pages + Access）は AWS 側設定値の越境読み書きが必要で構成が複雑になるため不採用。キーワードルール単独は AWS 側の言い回し変化に弱く、LLM 単独は挙動の予測可能性が下がるため二段構えとした。分類は Judge 役（temperature=0・揺らぎ排除）、カテゴリ提案は Generator 役（揺らぎ許容）と役割を分ける。

### Phase 2（確定・2026-07-09 着手）: 図解の自動生成エージェント
このサービスの本質。1 記事ごとに「グラフィカルに解説した図解」をオンデマンド生成して LINE に届ける。原型は `~/projects/aws-whatnew-visual/`（codex に「サービス名＋本文」を渡して1枚の解説画像を生成する実験）。名前が示す通り Phase 1 の決定論パイプラインと違い、ツールを叩く**エージェント構成**を取る。

#### 起動と配信（オンデマンド）
- 各記事の Flex カードに **「グラフィカル解説」ボタン**を追加（既存の「詳細」「Not for Me」に並べる 3 つ目）。押すと postback `action=explain&sid=<short_id>`。
- 生成は数十秒〜1分超かかるため**非同期**にする: webhook は即 200 を返し、その場で「図解を生成中です」と返信（reply）。裏で AgentCore を非同期 invoke し、完成後に **LINE Push** で結果を送る（reply トークンは短命なので使わない）。
- 成果物は **HTML を S3 に置き presigned URL を Push**（「📊 図解を開く」リンク）。PNG 化はしない — LINE 画像インライン表示が要るとき初めて足す。理由: HTML はズーム可・レスポンシブ・文字が確実に鮮明で、スマホで密な日本語図解を読むのに固定 PNG より優れ、描画工程（Chrome/AgentCore Browser）も不要で堅牢・安価。原型検証（`~/projects/aws-whatnew-visual/html_test/`）で GPT-5.5→自己完結HTML→表示が問題ないことを実測済み。

#### エージェント構成（全て IAM で閉じる・外部キーゼロ）
```
LINE「グラフィカル解説」ボタン → postback
  → API Gateway / Function URL → webhook Lambda（即200＋「生成中」reply＋非同期起動）
  → AgentCore Runtime のエージェント
      ① DynamoDB から記事情報取得（feedback mapping: short_id → article）
      ② AWS Knowledge MCP でサービス詳細を取得（原型の「手書き本文」の本番代替。未接続時は記事 description にフォールバック）
      ③ Bedrock の OpenAI GPT-5.5 を converse で呼ぶ → 自己完結 HTML（テキスト）が返る
      ④ S3 に .html を put（Content-Type: text/html）
      ⑤ presigned URL 発行（有効期限 ~1h）
      ⑥ LINE Push で「📊 図解を開く」リンク送信
```

#### 技術判断（根拠）
- **画像生成エンジン = GPT-5.5 が HTML を書く方式（案C）**。比較した 3 案:
  - A: OpenAI Images API(gpt-image) 直叩き — 原型と同一の絵だが gpt-image は Bedrock 非対応で**唯一 OpenAI キーが要る**。長期キーゼロ運用に反するため不採用。
  - B: Bedrock 純正画像モデル(Nova Canvas 等) — IAM で閉じるが拡散モデルは**日本語インフォグラフィック文字が崩れやすく**品質が賭けになるため不採用。
  - **C（採用）**: Bedrock 上の OpenAI モデルは公式に「text in / text out」のみ（画像は出せない）。だが SVG/HTML は**テキスト**なので GPT-5.5 が書ける。描画は resvg/ブラウザではなく**ブラウザ表示に委ねる**（HTML 直配信）。**全 IAM・キーゼロ・日本語確実・原型に近いベクター図解**で三案中もっとも要件に合致。
- **なぜ OpenAI キーが不要か**: OpenAI モデルは 2026-06-01 に Bedrock ネイティブ GA（GPT-5.5/5.4/Codex）。`bedrock:InvokeModel` を IAM で叩くだけで呼べる。認証は AWS 側で完結。
- **リージョン**: GPT-5.5 は US East (Ohio, us-east-2)。本スタックは us-east-1。→ 図解の Bedrock 呼び出しだけ **us-east-2** のクライアントを使う（`EXPLAINER_BEDROCK_REGION`）。要約(Nova)は従来通り us-east-1。
- **なぜ AgentCore か**: オンデマンド・ツール（MCP）駆動・複数ステップという性質が Runtime 向き。将来の深掘り/複数ソース横断もここに載る。名前（*agent*）の通りの構成。

#### Phase 2 の内訳（マイルストーン）
- 2.1 起動経路: Flex に「グラフィカル解説」ボタン追加 → webhook で `action=explain` を処理 → 即「生成中」reply ＋ AgentCore 非同期 invoke（空実装で経路を通す）。
- 2.2 エージェント本体: 記事取得 → (MCP) → GPT-5.5 → 自己完結 HTML → S3 → presigned → LINE Push。framework 非依存のコア（`src/explainer.py`）＋ AgentCore Runtime エントリポイント（`agent/`）。
- 2.3 デプロイ＆観測: `agentcore launch`（Runtime）＋ `cdk deploy`（S3/IAM/権限）＋ LINE ボタン実機確認 ＋ プロンプト/レイアウト調整（原型検証で見えた下端はみ出し対策）。**←ここはてつてつの `aws login` 後**。

#### 本 Phase の完了条件（DoD）
「配信済み記事の『グラフィカル解説』ボタンを押すと、数十秒後に自分の LINE へ『📊 図解を開く』リンクが Push され、開くとその AWS 更新をグラフィカルに解説した自己完結 HTML が表示される。生成失敗時はユーザーに失敗が分かるメッセージが届き、ログに残る。」

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
- 関心サービス／除外サービスのフィルタ条件 → **2026-07-08 解決: Phase 1.5 のカテゴリフィルタとして確定（spec.md §9）**
- 状態ストア: DynamoDB か S3 か
- 要約モデルの最終決定（Nova 実測後）
- Phase 2 のエージェント要件（次の議論の主題）
