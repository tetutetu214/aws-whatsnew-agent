"""webhook から AgentCore Runtime を非同期起動するトリガ。

webhook Lambda は 60 秒でタイムアウトし即 200 を返す必要があるため、図解生成
（数十秒〜1分超）はここでブロックせず投げっぱなしにする。既定は AgentCore Runtime を
invoke_agent_runtime で叩く。テストではフェイク client / 注入 trigger で検証する。
"""

from typing import Any
import json
import logging
import os

LOGGER = logging.getLogger(__name__)


def invoke_explainer(
    short_id: str,
    runtime_arn: str | None = None,
    client: Any | None = None,
) -> None:
    runtime_arn = runtime_arn or os.environ.get("AGENT_RUNTIME_ARN", "")
    if not runtime_arn:
        # 未デプロイ（ARN 未設定）の間は静かにスキップ。デプロイ後に効き始める。
        LOGGER.warning("AGENT_RUNTIME_ARN not set; skip explainer invoke")
        return

    if client is None:
        import boto3

        client = boto3.client("bedrock-agentcore")

    client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        payload=json.dumps({"short_id": short_id}).encode("utf-8"),
    )
