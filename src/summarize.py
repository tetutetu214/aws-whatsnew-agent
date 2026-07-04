from typing import Any
import logging

try:
    from .rss import Article
except ImportError:
    from rss import Article


LOGGER = logging.getLogger(__name__)
SYSTEM_PROMPT = (
    "AWSの新機能更新を、日本語で1〜2行、事実ベースで、"
    "誇張・季節挨拶なしに要約してください。"
)


def summarize_article(
    article: Article,
    model_id: str,
    bedrock_client: Any | None = None,
) -> str:
    if bedrock_client is None:
        import boto3

        bedrock_client = boto3.client("bedrock-runtime")

    try:
        response = bedrock_client.converse(
            modelId=model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                f"タイトル: {article.title}\n"
                                f"説明: {article.description}"
                            )
                        }
                    ],
                }
            ],
            inferenceConfig={
                "maxTokens": 120,
                "temperature": 0.2,
            },
        )
        summary = _extract_text(response)
        return summary or article.title
    except Exception as error:
        LOGGER.warning(
            "Bedrock summarize failed; using title fallback: %s",
            type(error).__name__,
        )
        return article.title


def _extract_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    texts = [
        item.get("text", "").strip()
        for item in content
        if isinstance(item, dict) and item.get("text")
    ]
    return "\n".join(texts).strip()
