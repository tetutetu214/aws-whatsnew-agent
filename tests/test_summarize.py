from src.rss import Article
from src.summarize import summarize_article


class SuccessfulBedrockClient:
    def converse(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        return {
            "output": {
                "message": {
                    "content": [
                        {"text": "日本語の要約です。"},
                    ]
                }
            }
        }


class FailingBedrockClient:
    def converse(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        raise RuntimeError("bedrock error")


def test_bedrockが正常応答した時は要約文を返す() -> None:
    article = _article()

    summary = summarize_article(
        article,
        model_id="amazon.nova-micro-v1:0",
        bedrock_client=SuccessfulBedrockClient(),
    )

    assert summary == "日本語の要約です。"


def test_bedrockが例外を返した時はタイトルへフォールバックする() -> None:
    article = _article()

    summary = summarize_article(
        article,
        model_id="amazon.nova-micro-v1:0",
        bedrock_client=FailingBedrockClient(),
    )

    assert summary == "Amazon Bedrock update"


def _article() -> Article:
    return Article(
        article_id="article-1",
        title="Amazon Bedrock update",
        link="https://example.com/bedrock",
        description="description",
        published="Mon, 06 Jul 2026 00:00:00 GMT",
    )
