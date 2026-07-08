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
        ProjectionExpression: str | None = None,
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

    def update_item(
        self,
        TableName: str,
        Key: dict[str, dict[str, str]],
        UpdateExpression: str,
        ExpressionAttributeValues: dict[str, dict[str, str]],
    ) -> None:
        del TableName, UpdateExpression
        article_id = Key["article_id"]["S"]
        self.items.setdefault(article_id, {"article_id": {"S": article_id}})
        self.items[article_id]["feedback"] = ExpressionAttributeValues[":feedback"]
        self.items[article_id]["feedback_at"] = (
            ExpressionAttributeValues[":feedback_at"]
        )

    def scan(self, TableName: str) -> dict[str, list[dict[str, dict[str, str]]]]:
        del TableName
        return {"Items": list(self.items.values())}


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


def test_filtered記録にはカテゴリが保存される() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")

    store.mark_filtered(article, "region_expansion")

    item = client.items["article-1"]
    assert item["status"] == {"S": "filtered"}
    assert item["category"] == {"S": "region_expansion"}


def test_feedback対応レコードはfbプレフィックスのキーで保存される() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")

    store.save_feedback_mapping("abc123", article, "other")

    item = client.items["fb#abc123"]
    assert item["article_ref"] == {"S": "article-1"}
    assert item["category"] == {"S": "other"}


def test_feedback対応レコードから元記事を取得できる() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")
    store.save_feedback_mapping("abc123", article, "other")

    mapping = store.get_feedback_mapping("abc123")

    assert mapping == {
        "article_id": "article-1",
        "title": "title",
        "category": "other",
    }


def test_dislike記録はsent記事へfeedback属性を追記する() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")
    store.mark_sent(article)

    store.mark_dislike("article-1")

    item = client.items["article-1"]
    assert item["feedback"] == {"S": "dislike"}
    assert "feedback_at" in item


def test_scan_feedback_itemsはDynamoDB属性を文字列dictへ変換する() -> None:
    client = FakeDynamoDbClient()
    store = SentArticleStore("table", dynamodb_client=client)
    article = _article("article-1")
    store.mark_sent(article)
    store.mark_dislike("article-1")

    items = store.scan_feedback_items()

    assert items[0]["article_id"] == "article-1"
    assert items[0]["feedback"] == "dislike"


class PagingScanClient:
    # Scan の 1MB 分割（LastEvaluatedKey）を再現する fake
    def __init__(self) -> None:
        self.pages = [
            {
                "Items": [
                    {"article_id": {"S": "a-1"}, "feedback": {"S": "dislike"}}
                ],
                "LastEvaluatedKey": {"article_id": {"S": "a-1"}},
            },
            {"Items": [{"article_id": {"S": "a-2"}}]},
        ]
        self.start_keys: list[object] = []

    def scan(
        self,
        TableName: str,
        ExclusiveStartKey: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, object]:
        del TableName
        self.start_keys.append(ExclusiveStartKey)
        return self.pages[len(self.start_keys) - 1]


def test_scanが1MBで分割されても全ページを辿って返す() -> None:
    client = PagingScanClient()
    store = SentArticleStore("table", dynamodb_client=client)

    items = store.scan_feedback_items()

    assert [item["article_id"] for item in items] == ["a-1", "a-2"]
    assert client.start_keys == [None, {"article_id": {"S": "a-1"}}]


def _article(article_id: str) -> Article:
    return Article(
        article_id=article_id,
        title="title",
        link=f"https://example.com/{article_id}",
        description="description",
        published="Mon, 06 Jul 2026 00:00:00 GMT",
    )
