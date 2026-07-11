# aws-whatsnew-agent

AWS の新機能情報（What's New）を毎朝要約して LINE に届け、さらに各記事を **AI エージェントがその場でグラフィカルな図解に変換**するサービス。

- **Phase 1 / 1.5（決定論パイプライン・稼働中）**: What's New RSS → ルール＋LLM でフィルタ → Amazon Bedrock (Nova Micro) で日本語要約 → LINE に 1 記事 = 1 Flex カードで配信。各カードに「Not for Me」フィードバックボタン。
- **Phase 2（エージェント・稼働中）**: カードの「グラフィカル解説」ボタンを押すと、**Amazon Bedrock AgentCore Runtime**（サーバレス）上のエージェントが、記事情報に **AWS Knowledge MCP** で取得したサービス詳細を加え、**Claude Sonnet 5 で密な日本語インフォグラフィック HTML** を生成。私有 S3 に置き、閲覧用 Lambda の短い URL を LINE に Push する（スマホ対応のレスポンシブ HTML）。

すべて IAM で完結し、長期キーは持たない。詳細は [`docs/plan.md`](docs/plan.md) / [`docs/spec.md`](docs/spec.md) / [`docs/agentcore-plan.md`](docs/agentcore-plan.md)。

## 構成図

左が **Phase 1 / 1.5（毎朝の配信）**、右が **Phase 2（図解エージェント）**。中央の **LINE** と **DynamoDB** を両フェーズで共有する。Phase 1 が配ったカードの「グラフィカル解説」ボタンが Phase 2 を起動する。

```mermaid
flowchart LR
  subgraph P1["Phase 1 / 1.5 ― 毎朝の要約配信"]
    direction TB
    SCH["EventBridge Scheduler<br/>毎朝 7:00 JST"] --> W["Worker Lambda"]
    RSS["What's New RSS"] --> W
    W --> FIL{"フィルタ<br/>ルール → Nova 分類"}
    FIL -->|配信| SUM["Bedrock Nova Micro<br/>日本語要約"]
    SUM --> CARD["LINE Flex カード<br/>詳細 / Not for Me / グラフィカル解説"]
  end

  LINE(("LINE ／<br/>ユーザー"))
  DDB[("DynamoDB<br/>記事・既読・feedback")]

  subgraph P2["Phase 2 ― 図解生成エージェント（オンデマンド）"]
    direction TB
    WH["Webhook Lambda<br/>(Function URL)"] --> DIS["Dispatcher Lambda<br/>Event 非同期"]
    DIS --> AC["AgentCore Runtime<br/>Strands・サーバレス"]
    AC --> MCP["AWS Knowledge MCP<br/>サービス詳細"]
    AC --> CLA["Bedrock<br/>Claude Sonnet 5<br/>密な日本語 HTML"]
    CLA --> S3[("S3（私有）")]
    VIEW["Viewer Lambda<br/>(Function URL)"] --> S3
  end

  CARD ==> LINE
  LINE ==>|「グラフィカル解説」を押す| WH
  AC ==>|図解リンクを Push| LINE
  LINE ==>|リンクをタップ| VIEW
  W -. 記事を保存 .-> DDB
  AC -. 記事を取得 .-> DDB
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
Python 3.12 / AWS（us-east-1）/ Amazon Bedrock（Nova Micro・Claude Sonnet 5）/ Amazon Bedrock AgentCore / AWS Knowledge MCP / AWS CDK / LINE Messaging API
