from src.classify import OTHER_CATEGORY, classify_article
from src.filter_config import DEFAULT_FILTER_CONFIG, toggle_category
from src.rss import Article


# 実 AWS 未認証環境のため Bedrock は fake client で代替する。
class RecordingBedrockClient:
    def __init__(self, text: str = OTHER_CATEGORY, fail: bool = False) -> None:
        self.text = text
        self.fail = fail
        self.calls = 0

    def converse(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        self.calls += 1
        if self.fail:
            raise RuntimeError("bedrock error")
        return {
            "output": {
                "message": {
                    "content": [
                        {"text": self.text},
                    ]
                }
            }
        }


def test_ルール一致時はLLMを呼ばずカテゴリを返す() -> None:
    client = RecordingBedrockClient()

    category = classify_article(
        _article("Amazon RDS is now available in Asia Pacific Regions"),
        DEFAULT_FILTER_CONFIG,
        "amazon.nova-micro-v1:0",
        bedrock_client=client,
    )

    assert category == "region_expansion"
    assert client.calls == 0


def test_無効カテゴリにルール一致しても通過扱いになる() -> None:
    client = RecordingBedrockClient(OTHER_CATEGORY)
    current = toggle_category(DEFAULT_FILTER_CONFIG, "region_expansion")

    category = classify_article(
        _article("Amazon RDS is now available in Asia Pacific Regions"),
        current,
        "amazon.nova-micro-v1:0",
        bedrock_client=client,
    )

    assert category == OTHER_CATEGORY
    assert client.calls == 1


def test_LLMが有効カテゴリを返した時はそのカテゴリを返す() -> None:
    client = RecordingBedrockClient("instance_size")

    category = classify_article(
        _article("Amazon EC2 update"),
        DEFAULT_FILTER_CONFIG,
        "amazon.nova-micro-v1:0",
        bedrock_client=client,
    )

    assert category == "instance_size"


def test_LLMがenum外応答を返した時はotherへフォールバックする() -> None:
    client = RecordingBedrockClient("unknown_category")

    category = classify_article(
        _article("Amazon EC2 update"),
        DEFAULT_FILTER_CONFIG,
        "amazon.nova-micro-v1:0",
        bedrock_client=client,
    )

    assert category == OTHER_CATEGORY


def test_LLMが例外を返した時はotherへフォールバックする() -> None:
    client = RecordingBedrockClient(fail=True)

    category = classify_article(
        _article("Amazon EC2 update"),
        DEFAULT_FILTER_CONFIG,
        "amazon.nova-micro-v1:0",
        bedrock_client=client,
    )

    assert category == OTHER_CATEGORY


def test_対応インスタンスタイプ拡大の記事はregion扱いにならずinstance_sizeに確定する() -> None:
    # 「in all commercial regions」を含むためかつては region_expansion に
    # 誤爆していた実データケース（2026-07-08）。実態はインスタンスタイプ対応拡大
    client = RecordingBedrockClient(OTHER_CATEGORY)

    category = classify_article(
        _article(
            "Amazon Time Sync Service adds support for Microsecond accurate "
            "time on 26 additional EC2 instance types in all commercial regions"
        ),
        DEFAULT_FILTER_CONFIG,
        "amazon.nova-micro-v1:0",
        bedrock_client=client,
    )

    assert category == "instance_size"
    assert client.calls == 0


def test_regions言及だけの機能追加記事はルール確定せずLLM判定に委ねる() -> None:
    # regions という語があっても available 等の展開表現がなければルールで落とさない
    client = RecordingBedrockClient(OTHER_CATEGORY)

    category = classify_article(
        _article(
            "AWS Config now supports 8 new resource types in all commercial regions"
        ),
        DEFAULT_FILTER_CONFIG,
        "amazon.nova-micro-v1:0",
        bedrock_client=client,
    )

    assert category == OTHER_CATEGORY
    assert client.calls == 1


def _article(title: str) -> Article:
    return Article(
        article_id="article-1",
        title=title,
        link="https://example.com/article-1",
        description="description",
        published="Mon, 06 Jul 2026 00:00:00 GMT",
    )
