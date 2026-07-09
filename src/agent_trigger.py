"""webhook → (非同期 Event Lambda) → AgentCore Runtime の2段トリガ。

webhook Lambda は 60 秒でタイムアウトし即 200 を返す必要があるが、図解生成は数十秒〜1分超。
`invoke_agent_runtime` は同期 API なので webhook から直接叩くとブロックしてタイムアウト →
LINE が webhook を再送 → reply token 使い回しエラー＋二重生成、を招く。

そこで webhook は dispatcher Lambda を `InvocationType=Event` で投げっぱなしにし（数ミリ秒で復帰）、
dispatcher が `invoke_agent_runtime` で AgentCore Runtime を起動する。dispatcher は webhook の
クリティカルパス外なので AgentCore の完了まで待って構わない（timeout を長くする）。
"""

from typing import Any
import json
import logging
import os

LOGGER = logging.getLogger(__name__)


def dispatch_async(
    short_id: str,
    function_name: str | None = None,
    client: Any | None = None,
) -> None:
    """webhook から呼ぶ。dispatcher Lambda を非同期(Event)起動して即戻る（fire-and-forget）。"""
    function_name = function_name or os.environ.get("EXPLAINER_DISPATCHER_FUNCTION", "")
    if not function_name:
        # 未デプロイ（関数名未設定）の間は静かにスキップ。デプロイ後に効き始める。
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


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """dispatcher Lambda のエントリ。Event で short_id を受け AgentCore を起動する。"""
    del context
    short_id = str(event.get("short_id", "")).strip()
    if short_id:
        invoke_agent_runtime(short_id)
    return {"short_id": short_id}


def invoke_agent_runtime(
    short_id: str,
    runtime_arn: str | None = None,
    client: Any | None = None,
) -> None:
    runtime_arn = runtime_arn or os.environ.get("AGENT_RUNTIME_ARN", "")
    if not runtime_arn:
        # ARN 未設定（launch 前）の間は静かにスキップ。
        LOGGER.warning("AGENT_RUNTIME_ARN not set; skip agent runtime invoke")
        return
    if client is None:
        import boto3

        client = boto3.client("bedrock-agentcore")
    client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        payload=json.dumps({"short_id": short_id}).encode("utf-8"),
    )
