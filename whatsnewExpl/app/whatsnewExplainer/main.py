"""AgentCore Runtime エントリポイント（図解生成エージェント）。

創設時の設計フロー: short_id を受け取り → ① DynamoDB の既存記事情報 → ② AWS Knowledge MCP で
そのサービスの詳細 → ③ Bedrock(OpenAI)モデルが①②で内容構成 → 自己完結HTML → ④ 私有S3 →
閲覧Lambda の短いURLを LINE Push。重いロジックはテスト済みの explainer/aws_mcp に委譲する。

AgentCore Runtime は CodeZip・サーバレス。webhook→dispatcher(Event)→invoke_agent_runtime で
このエントリが起動される。payload = {"short_id": "..."}。
"""

import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

import aws_mcp
import explainer
import store

app = BedrockAgentCoreApp()
log = app.logger


def _mcp_call(title: str, link: str) -> str:
    # サービス名（記事タイトル）で AWS Knowledge MCP を引き、図解入力を富化する。
    del link
    return aws_mcp.fetch_service_context(title)


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    del context
    short_id = str(payload.get("short_id", "")).strip()
    if not short_id:
        # 素の prompt 文字列で来た場合のフォールバック（agentcore invoke "xxx" 等）
        short_id = str(payload.get("prompt", "")).strip()
    if not short_id:
        return {"status": "error", "reason": "missing short_id"}

    log.info("explainer invoke short_id=%s", short_id)
    config = explainer.load_explainer_config()
    article_store = store.SentArticleStore(
        table_name=os.environ.get("TABLE_NAME", "aws-whatsnew-agent-sent"),
    )
    result = explainer.generate_explainer(
        short_id,
        article_store,
        config,
        mcp_call=_mcp_call,
    )
    log.info("explainer result=%s", result.get("status"))
    return result


if __name__ == "__main__":
    app.run()
