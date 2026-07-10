# AgentCore 版 図解エージェント — 検証済み設計（2026-07-11）

このプロジェクトの創設時の前提（プロジェクト名 aws-whatsnew-**agent**）：
**LINE で図解ボタン → AgentCore が動く → 既存の AWS 記事情報 ＋ そのサービスの情報を MCP で取得 → モデルが内容構成 → HTML で出す。**

2026-07-10〜11 に、非推奨警告に引きずられて一旦 AgentCore を外した Lambda v1 を本番投入したが、
てつてつの指摘で本来の AgentCore + MCP 構成に戻す。以下は**実物で検証した事実**（推測でない）。

## 検証済みの事実
- **AgentCore Runtime はサーバレス**。ビルド形式デフォルトは **CodeZip（Python を zip して S3、Docker/ECR 不要）**。コンテナは任意。→ 「コンテナが必須/重い」は誤りだった。
- 正式 CLI は **`@aws/agentcore`（npm）**。`agentcore create` → `agentcore deploy`（CDK ベース）。pip の starter-toolkit は非推奨。
- `agentcore create` の雛形（Strands・Bedrock・CodeZip・HTTP）は **MCP クライアント込み**（`app/<name>/mcp_client/client.py` が streamable HTTP MCP を返し、`main.py` が tools に載せる）。実行した生成コマンド:
  ```
  agentcore create --name whatsnewExplainer --project-name whatsnewExpl \
    --defaults --build CodeZip --language Python --framework Strands \
    --model-provider Bedrock --protocol HTTP --memory none
  ```
- **AWS Knowledge MCP（認証不要・リモート）から自前コードで実データ取得できる**。
  - エンドポイントは **ベース URL `https://knowledge-mcp.global.api.aws`**（**`/mcp` を付けると tool-call が「Http operation is not supported for gateway protocol type MCP」で 400**。公式 mcp クライアントでもベース URL なら成功）。
  - ツール: `aws___search_documentation`（`search_phrase` 必須, `limit`, `topics`）/ `aws___read_documentation`（`requests:[{url,max_length,start_index}]`）ほか。
  - 実装は `src/aws_mcp.py`（公式 `mcp` クライアント・遅延 import・runner 注入でテスト可）。pytest 4 件。
- **MCP 富化の効果を実証**。SageMaker Feature Store で、RSS の title だけの薄い図（一般的な埋め草「CSV, Parquet…」）が、MCP 由来の API 事実（BatchWriteRecord API / list_records API / TTL 自動ハード削除 / TargetStores 指定可）に置き換わり、正確になった。
- 生成モデルは **`openai.gpt-oss-120b-1:0`（us-east-1・IAM のみ・推論プロファイル不要）**で稼働実績。GPT-5.5(us-east-2)へは env 切替。

## AgentCore 版の構成（次セッションで実装・デプロイ）
```
LINE「グラフィカル解説」ボタン(実装済) → webhook 即200＋「生成中」reply(実装済)
  → dispatcher Lambda(実装済) が AgentCore Runtime を非同期起動
  → AgentCore(Strands, CodeZip, サーバレス) のエージェント:
      ① DynamoDB から記事情報（既存 feedback mapping。title/link/description）
      ② AWS Knowledge MCP でサービス詳細（src/aws_mcp.py 相当を Strands MCPClient で）
      ③ Bedrock(gpt-oss→GPT-5.5) が ①② で内容構成 → 自己完結 HTML
      ④ 私有 S3 に put → 閲覧 Lambda(実装済) の短い URL を LINE Push(実装済)
```
再利用できる既存資産（捨てない）: `src/explainer.py`(build_html/S3/URL/Push), `src/viewer.py`(閲覧), `src/store.py`(記事取得), `src/line.py`(Push), `src/aws_mcp.py`(MCP富化), 私有S3・閲覧Lambda・dispatcher（デプロイ済）。

## 残ステップ（要 てつてつ立ち会い＝deploy 承認）
1. `agentcore create`（上記コマンド）で雛形を repo 内に生成し、`mcp_client/client.py` の endpoint を `https://knowledge-mcp.global.api.aws` に変更。
2. `main.py` の entrypoint を「短い agentic ループ or 制御フロー」で ①〜④ を実行（explainer/aws_mcp のロジックを移植 or 依存として同梱）。pyproject に `mcp`, `boto3` を追加。
3. `agentcore dev` でローカル起動 → 実 invoke で HTML 生成を確認（AWS 認証あり）。
4. `agentcore deploy`（CodeZip・サーバレス。**本番 deploy は auto モードの承認が要るため てつてつ実行**）。runtime ARN を dispatcher の `AGENT_RUNTIME_ARN` に設定。
5. dispatcher を「generate_explainer 直接実行」から「invoke_agent_runtime」へ戻す（agent_trigger に両実装あり）。
6. LINE 実機でボタンタップ → 富化された図解が届くのを E2E 確認。

## 注意
- Lambda(stdlib のみ・from_asset("src"))には `mcp` パッケージが同梱されない。MCP 富化は**依存管理がある AgentCore CodeZip 側**に置くのが正しい（現行 Lambda dispatcher にそのまま入れると import エラー）。だから MCP は AgentCore 移行とセット。
- 現行 Lambda v1（MCP なし・gpt-oss）は本番で動いたまま。AgentCore 版が deploy できたら webhook の向き先を切り替える。後退なし。
