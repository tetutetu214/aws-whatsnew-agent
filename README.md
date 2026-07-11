# aws-whatsnew-agent

AWS の新機能情報（What's New）を毎朝要約して LINE に届け、さらに各記事を **AI エージェントがその場でグラフィカルな図解に変換**するサービス。

- **Phase 1 / 1.5（決定論パイプライン・稼働中）**: What's New RSS → ルール＋LLM でフィルタ → Amazon Bedrock (Nova Micro) で日本語要約 → LINE に 1 記事 = 1 Flex カードで配信。各カードに「Not for Me」フィードバックボタン。
- **Phase 2（エージェント・稼働中）**: カードの「グラフィカル解説」ボタンを押すと、**Amazon Bedrock AgentCore Runtime**（サーバレス）上のエージェントが、記事情報に **AWS Knowledge MCP** で取得したサービス詳細を加え、**Claude Sonnet 4.6 で密な日本語インフォグラフィック HTML** を生成。私有 S3 に置き、閲覧用 Lambda の短い URL を LINE に Push する（スマホ対応のレスポンシブ HTML）。

すべて IAM で完結し、長期キーは持たない。詳細は [`docs/plan.md`](docs/plan.md) / [`docs/spec.md`](docs/spec.md) / [`docs/agentcore-plan.md`](docs/agentcore-plan.md)。

## 構成図

上から下へ1つの流れで読む。**青 = Phase 1 / 1.5（毎朝の配信）**、**オレンジ = Phase 2（図解エージェント）**。中央の「ボタンを押す」が2つのフェーズをつなぐ。

```mermaid
flowchart TD
  SCH["EventBridge Scheduler（毎朝 7:00 JST）"] --> W["Worker Lambda"]
  RSS["AWS What's New RSS"] --> W
  W --> FIL["フィルタ（ルール → Nova で分類）"]
  FIL --> SUM["Bedrock Nova Micro で日本語要約"]
  SUM --> CARD["LINE に Flex カードを配信<br/>（詳細 / Not for Me / グラフィカル解説）"]
  CARD --> TAP(["ユーザーが「グラフィカル解説」ボタンを押す"])
  TAP --> WH["Webhook Lambda（即「生成中」と返信）"]
  WH --> DIS["Dispatcher Lambda（Event で非同期に起動）"]
  DIS --> AC["AgentCore Runtime（サーバレス）が処理を実行"]
  AC --> MCP["AWS Knowledge MCP でサービス詳細を取得"]
  MCP --> GEN["Bedrock Claude Sonnet 4.6 で密な日本語 HTML を生成"]
  GEN --> S3["S3（私有）に図解 HTML を保存"]
  S3 --> PUSH["Viewer Lambda の短い URL を LINE に Push"]
  PUSH --> DONE(["ユーザーがタップして図解を閲覧"])

  DB[("DynamoDB<br/>記事・既読・feedback")]
  W -. 記事を保存 .-> DB
  AC -. 記事を取得 .-> DB

  classDef p1 fill:#e8f0ff,stroke:#3f6fd1,color:#12233f;
  classDef p2 fill:#fff2e0,stroke:#e08a00,color:#3a2a00;
  classDef ext fill:#f2f2f2,stroke:#9aa0a6,color:#222;
  class SCH,RSS,W,FIL,SUM,CARD p1;
  class WH,DIS,AC,MCP,GEN,S3,PUSH p2;
  class TAP,DONE,DB ext;
```

**要点**
- 図解生成は数分かかるため **webhook → dispatcher(Event 非同期) → AgentCore** の2段で、webhook は即「生成中」を返して即応する。
- webhook は LINE 署名（チャネルシークレットの HMAC）を検証し、正当なリクエストのみ処理する。
- presigned URL は LINE の URI ボタン上限(1000字)を超えるため、**バケットは私有のまま Viewer Lambda が短い URL で配信**する。生成物は **スマホ対応のレスポンシブ HTML**。
- 図解の内容は「**今回のアップデートで既存がどう変わったか**」を主役（約6割）、サービスの背景（MCP 由来）を補足（約4割）に配分する。

## 構成 / デプロイ（2 スタック）

| 対象 | 実体 | デプロイ |
| --- | --- | --- |
| Worker / Webhook / Dispatcher / Viewer / S3 / DynamoDB / Scheduler / アラート | AWS CDK (Python) `stacks/` | `cdk deploy`（`AwsWhatsNewAgentStack`） |
| 図解エージェント本体 | AgentCore プロジェクト `whatsnewExpl/`（Strands・CodeZip） | `agentcore deploy`（`@aws/agentcore` CLI） |

- LINE トークン等のシークレットは Git 管理外（SSM SecureString / `~/.secrets/`）。リポジトリには `.env.example` のみ。
- `whatsnewExpl/agentcore/aws-targets.json`（デプロイ先アカウント）は各自ローカルに作成する（`aws-targets.example.json` 参照）。

## 技術スタック
Python 3.12 / AWS（us-east-1）/ Amazon Bedrock（Nova Micro・Claude Sonnet 4.6）/ Amazon Bedrock AgentCore / AWS Knowledge MCP / AWS CDK / LINE Messaging API
