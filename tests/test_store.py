# サンドボックスに AWS 認証・ネットワークが無く、moto も依存追加できないため fake client で代替。
from src.rss import Article
from src.store import SentArticleStore


class FakeDynamoDbClient:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, dict[str, str]]] = {}

    def get_item(
        self,
        TableName: str,
        Key: dict[str, dict[str, str]],
        ProjectionExpression: str,
    ) -> dict[str, dict[str, dict[str, str]]]:
        del TableName, ProjectionExpression
        article_id = Key["article_id"]["S"]
        if article_id not in self.items:
            return {}
        return {"Item": self.items[article_id]}

    def put_item(
        self,
        TableName: str,
        Item: dict[str, dict[str, str]],
    ) -> None:
        del TableName
        self.items[Item["article_id"]["S"]] = Item


def test_未登録の記事は未送信として判定される() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)

    assert store.is_unsent("article-1") is True


def test_sent記録後の記事は未送信として扱われない() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")

    store.mark_sent(article)

    assert store.is_unsent("article-1") is False
    assert client.items["article-1"]["status"]["S"] == "sent"
    assert "sent_at" in client.items["article-1"]


def test_seeded記録後の記事は未送信として扱われない() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")

    store.mark_seeded(article)

    assert store.is_unsent("article-1") is False
    assert client.items["article-1"]["status"]["S"] == "seeded"


def test_送信記録に要約文とモデルIDがS属性として保存される() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")

    store.mark_sent(article, summary="要約テキスト", model_id="amazon.nova-micro-v1:0")

    item = client.items["article-1"]
    assert item["summary"] == {"S": "要約テキスト"}
    assert item["model_id"] == {"S": "amazon.nova-micro-v1:0"}


def test_要約が空のときは要約とモデルID属性を付けない() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")

    store.mark_sent(article, summary="", model_id="")

    item = client.items["article-1"]
    assert "summary" not in item
    assert "model_id" not in item


def test_seeded記録には要約とモデルID属性を付けない() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")

    store.mark_seeded(article)

    item = client.items["article-1"]
    assert "summary" not in item
    assert "model_id" not in item


def _article(article_id: str) -> Article:
    return Article(
        article_id=article_id,
        title="title",
        link=f"https://example.com/{article_id}",
        description="description",
        published="Mon, 06 Jul 2026 00:00:00 GMT",
    )
