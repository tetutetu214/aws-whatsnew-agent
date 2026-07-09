"""AgentCore Runtime のエントリポイント。

webhook から invoke_agent_runtime で {"short_id": ...} を受け取り、src/explainer.py の
generate_explainer を実クライアントで実行する。重いロジックは explainer 側（テスト済み）に
あり、ここは AgentCore の受け口の薄いラッパーに徹する。

デプロイ: このディレクトリで `agentcore configure --entrypoint agent_runtime.py` → `agentcore launch`。
実行ロールに S3(PutObject/GetObject) / bedrock:InvokeModel(openai.*) / dynamodb:GetItem /
ssm:GetParameter(line token・user) を付与する（docs/spec.md §10.6）。
"""

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from explainer import generate_explainer, load_explainer_config
from store import SentArticleStore

app = BedrockAgentCoreApp()


@app.entrypoint
def handler(payload: dict[str, Any]) -> dict[str, Any]:
    short_id = str(payload.get("short_id", "")).strip()
    if not short_id:
        return {"status": "error", "reason": "missing short_id"}

    config = load_explainer_config()
    article_store = SentArticleStore(table_name=_table_name())
    return generate_explainer(short_id, article_store, config)


def _table_name() -> str:
    import os

    return os.environ.get("TABLE_NAME", "aws-whatsnew-agent-sent")


if __name__ == "__main__":
    app.run()
