"""webhook → dispatcher Lambda(Event 非同期) → AgentCore Runtime の2段トリガ。

webhook Lambda は 60 秒でタイムアウトし即 200 を返す必要があるが、図解生成は数十秒。
同期実行だと webhook をブロック → タイムアウト → LINE 再送 → 二重生成を招く。そこで webhook は
dispatcher Lambda を `InvocationType=Event` で投げっぱなしにし（数ミリ秒で復帰）、dispatcher が
AgentCore Runtime を `invoke_agent_runtime` で起動する（dispatcher は timeout 300s で完了を待つ）。

図解生成本体は AgentCore Runtime（whatsnewExpl/、サーバレス・CodeZip）側にあり、そこで
DynamoDB 記事 ＋ AWS Knowledge MCP ＋ Bedrock ＋ S3 ＋ LINE Push を実行する。
"""

from typing import Any
import json
import logging
import os
import uuid

LOGGER = logging.getLogger(__name__)


def dispatch_async(
    short_id: str,
    function_name: str | None = None,
    client: Any | None = None,
) -> None:
    """webhook から呼ぶ。dispatcher Lambda を非同期(Event)起動して即戻る（fire-and-forget）。"""
    function_name = function_name or os.environ.get("EXPLAINER_DISPATCHER_FUNCTION", "")
    if not function_name:
        LOGGER.warning("EXPLAINER_DISPATCHER_FUNCTION not set; skip explainer dispatch")
        return
    if client is None:
        import boto3

        client = boto3.client("lambda")
    client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps({"short_id": short_id}).encode("utf-8"),
    )


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    invoke: Any | None = None,
) -> dict[str, Any]:
    """dispatcher Lambda のエントリ。Event で short_id を受け AgentCore Runtime を起動する。"""
    del context
    short_id = str(event.get("short_id", "")).strip()
    if not short_id:
        return {"status": "error", "reason": "missing short_id"}
    runner = invoke or invoke_agent_runtime
    runner(short_id)
    return {"status": "dispatched", "short_id": short_id}


def invoke_agent_runtime(
    short_id: str,
    runtime_arn: str | None = None,
    client: Any | None = None,
) -> None:
    runtime_arn = runtime_arn or os.environ.get("AGENT_RUNTIME_ARN", "")
    if not runtime_arn:
        # ARN 未設定の間は静かにスキップ（デプロイ順序の保険）。
        LOGGER.warning("AGENT_RUNTIME_ARN not set; skip agent runtime invoke")
        return
    if client is None:
        import boto3

        client = boto3.client("bedrock-agentcore")
    # AgentCore は 33 文字以上のセッション ID を要求。生成ごとに独立セッションにする。
    session_id = f"whatsnew-{short_id}-{uuid.uuid4().hex}"[:64]
    client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        runtimeSessionId=session_id,
        payload=json.dumps({"short_id": short_id}).encode("utf-8"),
    )
