"""図解 HTML の閲覧用 Lambda（Function URL）。

presigned URL は SigV4 で1600文字超になり LINE の URI 上限(1000)を超える。そこで S3 バケットは
私有のままにし、この Lambda が `GET /?id=<short_id>` を受けて私有 S3 の explainer/<id>.html を
読み、text/html で返す。LINE には短い Function URL（`.../?id=<short_id>`）を渡す。

id は S3 キー injection・パストラバーサルを防ぐため 16進数(short_id と同形式)に限定する。
"""

from typing import Any
import logging
import os
import re

LOGGER = logging.getLogger(__name__)
# short_id は sha256 先頭12桁 = 16進。厳密に一致するものだけ許可する。
_ID_RE = re.compile(r"^[0-9a-f]{1,64}$")


def lambda_handler(
    event: dict[str, Any],
    context: Any,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    del context
    short_id = _extract_id(event)
    if not short_id or not _ID_RE.match(short_id):
        return _response(400, "text/plain; charset=utf-8", "invalid id")

    bucket = os.environ.get("EXPLAINER_BUCKET", "")
    key = f"explainer/{short_id}.html"
    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        html = obj["Body"].read().decode("utf-8")
    except Exception as error:
        LOGGER.info("viewer object not found: %s", type(error).__name__)
        return _response(404, "text/plain; charset=utf-8", "not found")
    return _response(200, "text/html; charset=utf-8", html)


def _extract_id(event: dict[str, Any]) -> str:
    params = event.get("queryStringParameters") or {}
    if params.get("id"):
        return str(params["id"]).strip()
    # Function URL は rawQueryString を渡すこともあるためフォールバック
    for part in (event.get("rawQueryString", "") or "").split("&"):
        if part.startswith("id="):
            return part[len("id=") :].strip()
    return ""


def _response(status: int, content_type: str, body: str) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": content_type},
        "body": body,
    }
