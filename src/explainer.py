"""Phase2: 記事を「グラフィカルに解説した自己完結 HTML」に変換して LINE に届けるエージェント本体。

framework 非依存の純粋関数＋クライアント注入で書く（既存モジュールの DI 規約に合わせる）。
AgentCore Runtime（agent/agent_runtime.py）からも、テストからも同じ関数を呼べる。

処理: mapping 取得 → (AWS MCP でサービス詳細) → Bedrock の OpenAI モデルで HTML 生成
      → S3 に put → presigned URL 発行 → LINE Push で「📊 図解を開く」リンク。
"""

from dataclasses import dataclass
from typing import Any
import logging
import os
import re

try:
    from . import line, store
except ImportError:
    import line
    import store


LOGGER = logging.getLogger(__name__)

# 確実に存在し IAM だけで呼べる OpenAI モデル（text-out）を既定にする。
# GPT-5.5（openai.gpt-5.5-*, us-east-2）へは EXPLAINER_MODEL_ID / EXPLAINER_BEDROCK_REGION で切替。
DEFAULT_EXPLAINER_MODEL_ID = "openai.gpt-oss-120b-1:0"
DEFAULT_EXPLAINER_REGION = "us-east-1"
DEFAULT_KEY_PREFIX = "explainer/"
DEFAULT_PRESIGN_EXPIRY = 3600
DEFAULT_LINE_TOKEN_PARAM = "/whatsnew-agent/line/channel_token"
DEFAULT_LINE_USER_ID_PARAM = "/whatsnew-agent/line/user_id"

# 原型（~/projects/aws-whatnew-visual/html_test/）で有効性を実測したプロンプト。
HTML_SYSTEM_PROMPT = (
    "あなたは AWS の技術更新を1枚の図解にするデザイナーです。"
    "与えられた AWS の更新内容を、グラフィカルに解説した1枚もののインフォグラフィックを、"
    "自己完結型の HTML として出力してください。厳守事項:\n"
    "- 出力は HTML のみ。前後に説明文やマークダウンのコードフェンス(```)を付けない。\n"
    "- 外部 CSS/JS/画像/Webフォント/CDN を一切参照しない。アイコンや図形はすべてインライン SVG で描く。\n"
    "- body 直下に幅1672px・高さ941px 固定の要素 .canvas を1つ置き、内容を必ずその中に収める"
    "（はみ出し・見切れ厳禁。要素数や文字量はキャンバスに収まる範囲に調整する）。\n"
    "- 情報設計: 大きなタイトルとサブタイトル / 入力→処理→ユースケースの流れ / 主要な特徴を"
    "下部にバッジで並べる、など本文の要点を視覚的に整理する。\n"
    "- 日本語は system-ui / sans-serif で崩れないようにする。"
    "配色は白背景＋AWSオレンジ(#FF9900)のアクセント＋濃紺(#232F3E)の見出し。"
)


@dataclass(frozen=True)
class ExplainerConfig:
    bucket: str
    model_id: str = DEFAULT_EXPLAINER_MODEL_ID
    bedrock_region: str = DEFAULT_EXPLAINER_REGION
    presign_expiry_seconds: int = DEFAULT_PRESIGN_EXPIRY
    key_prefix: str = DEFAULT_KEY_PREFIX
    line_token_param: str = DEFAULT_LINE_TOKEN_PARAM
    line_user_id_param: str = DEFAULT_LINE_USER_ID_PARAM


def load_explainer_config(environ: dict[str, str] | None = None) -> ExplainerConfig:
    values = environ if environ is not None else os.environ
    return ExplainerConfig(
        bucket=values.get("EXPLAINER_BUCKET", ""),
        model_id=values.get("EXPLAINER_MODEL_ID", DEFAULT_EXPLAINER_MODEL_ID),
        bedrock_region=values.get("EXPLAINER_BEDROCK_REGION", DEFAULT_EXPLAINER_REGION),
        presign_expiry_seconds=int(
            values.get("EXPLAINER_PRESIGN_EXPIRY", str(DEFAULT_PRESIGN_EXPIRY))
        ),
        key_prefix=values.get("EXPLAINER_KEY_PREFIX", DEFAULT_KEY_PREFIX),
        line_token_param=values.get("LINE_TOKEN_PARAM", DEFAULT_LINE_TOKEN_PARAM),
        line_user_id_param=values.get("LINE_USER_ID_PARAM", DEFAULT_LINE_USER_ID_PARAM),
    )


def fetch_service_context(
    title: str,
    link: str,
    mcp_call: Any | None = None,
) -> str:
    """AWS Knowledge MCP でサービス詳細を取得（原型の手書き本文の本番代替）。

    mcp_call 未注入時は空文字を返す（グレースフル。記事 description で代替される）。
    本番の MCP 配線は AgentCore Runtime 側で mcp_call を渡して有効化する。
    """
    if mcp_call is None:
        return ""
    try:
        return str(mcp_call(title, link) or "").strip()
    except Exception as error:
        LOGGER.warning("MCP context fetch failed: %s", type(error).__name__)
        return ""


def build_html(
    title: str,
    description: str,
    service_context: str,
    model_id: str,
    bedrock_client: Any,
) -> str:
    user_text = f"タイトル: {title}\n\n本文:\n{description}".strip()
    if service_context:
        user_text += f"\n\nサービス詳細（AWS ドキュメント）:\n{service_context}"

    response = bedrock_client.converse(
        modelId=model_id,
        system=[{"text": HTML_SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": 4000, "temperature": 0.4},
    )
    return _strip_code_fence(_extract_text(response))


def store_html(html: str, s3_client: Any, bucket: str, key: str) -> None:
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
    )


def presign(s3_client: Any, bucket: str, key: str, expires: int) -> str:
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


def build_link_message(url: str, title: str) -> dict[str, Any]:
    return {
        "type": "flex",
        "altText": f"図解ができました: {title}"[:400],
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "🎨 図解ができました",
                        "weight": "bold",
                    },
                    {"type": "text", "text": title, "wrap": True, "size": "sm"},
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "uri",
                            "label": "📊 図解を開く",
                            "uri": url,
                        },
                    }
                ],
            },
        },
    }


def generate_explainer(
    short_id: str,
    article_store: store.SentArticleStore,
    config: ExplainerConfig,
    mcp_call: Any | None = None,
    bedrock_client: Any | None = None,
    s3_client: Any | None = None,
    opener: Any | None = None,
    secrets_loader: Any | None = None,
) -> dict[str, Any]:
    # token/user_id が取れないと失敗通知すら送れないので最初に取得する（失敗時は素通しでログ）。
    token, user_id = (secrets_loader or _load_line_secrets)(
        config.line_token_param,
        config.line_user_id_param,
    )

    try:
        # DynamoDB 取得失敗も下の except で失敗通知できるよう try 内に入れる。
        mapping = article_store.get_feedback_mapping(short_id)
        if not mapping:
            line.push_messages(
                user_id,
                token,
                [{"type": "text", "text": "対象の記事が見つかりません"}],
                opener,
            )
            return {"status": "not_found", "short_id": short_id}

        bedrock_client = bedrock_client or _bedrock_client(config.bedrock_region)
        s3_client = s3_client or _s3_client()

        service_context = fetch_service_context(
            mapping.get("title", ""),
            mapping.get("link", ""),
            mcp_call,
        )
        html = build_html(
            mapping.get("title", ""),
            mapping.get("description", ""),
            service_context,
            config.model_id,
            bedrock_client,
        )
        if not html:
            raise RuntimeError("empty HTML from model")

        key = f"{config.key_prefix}{short_id}.html"
        store_html(html, s3_client, config.bucket, key)
        url = presign(
            s3_client, config.bucket, key, config.presign_expiry_seconds
        )
        line.push_messages(
            user_id,
            token,
            [build_link_message(url, mapping.get("title", ""))],
            opener,
        )
        return {"status": "sent", "short_id": short_id, "key": key, "url": url}
    except Exception as error:
        LOGGER.exception("Explainer failed: %s", type(error).__name__)
        line.push_messages(
            user_id,
            token,
            [{"type": "text", "text": "⚠️ 図解の生成に失敗しました"}],
            opener,
        )
        return {"status": "error", "short_id": short_id}


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    # モデルが ```html ... ``` で囲むことがあるため剥がす
    match = re.match(r"^```[a-zA-Z]*\n(.*)\n```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    texts = [
        item.get("text", "").strip()
        for item in content
        if isinstance(item, dict) and item.get("text")
    ]
    return "\n".join(texts).strip()


def _load_line_secrets(token_param: str, user_id_param: str) -> tuple[str, str]:
    import boto3

    ssm_client = boto3.client("ssm")
    token = ssm_client.get_parameter(Name=token_param, WithDecryption=True)[
        "Parameter"
    ]["Value"]
    user_id = ssm_client.get_parameter(Name=user_id_param, WithDecryption=True)[
        "Parameter"
    ]["Value"]
    return token, user_id


def _bedrock_client(region: str) -> Any:
    import boto3

    return boto3.client("bedrock-runtime", region_name=region)


def _s3_client() -> Any:
    import boto3

    return boto3.client("s3")
