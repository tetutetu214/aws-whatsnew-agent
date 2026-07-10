"""webhook → dispatcher Lambda(Event 非同期) の2段トリガ。

webhook Lambda は 60 秒でタイムアウトし即 200 を返す必要があるが、図解生成は数十秒〜1分超。
同期実行だと webhook をブロック → タイムアウト → LINE 再送 → 二重生成を招く。そこで webhook は
dispatcher Lambda を `InvocationType=Event` で投げっぱなしにし（数ミリ秒で復帰）、dispatcher が
図解生成本体（explainer.generate_explainer）を実行する。

v1 では dispatcher 自身が Bedrock(OpenAI) で HTML を生成する。将来 AWS MCP での深掘りが要る段で
AgentCore Runtime（agent/ に成果物あり）へ移す余地を残す。
"""

from typing import Any
import json
import logging
import os

try:
    from . import explainer, store
except ImportError:
    import explainer
    import store


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


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    generate: Any | None = None,
) -> dict[str, Any]:
    """dispatcher Lambda のエントリ。Event で short_id を受け図解生成を実行する。"""
    del context
    short_id = str(event.get("short_id", "")).strip()
    if not short_id:
        return {"status": "error", "reason": "missing short_id"}
    runner = generate or _run_explainer
    return runner(short_id)


def _run_explainer(short_id: str) -> dict[str, Any]:
    config = explainer.load_explainer_config()
    article_store = store.SentArticleStore(
        table_name=os.environ.get("TABLE_NAME", "aws-whatsnew-agent-sent"),
    )
    return explainer.generate_explainer(short_id, article_store, config)
