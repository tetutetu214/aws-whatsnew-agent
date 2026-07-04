from datetime import UTC, datetime, timedelta
from typing import Any

try:
    from .rss import Article
except ImportError:
    from rss import Article


class SentArticleStore:
    def __init__(
        self,
        table_name: str,
        dynamodb_client: Any | None = None,
        ttl_days: int = 90,
    ) -> None:
        self.table_name = table_name
        self.ttl_days = ttl_days
        if dynamodb_client is None:
            import boto3

            dynamodb_client = boto3.client("dynamodb")
        self.client = dynamodb_client

    def is_unsent(self, article_id: str) -> bool:
        response = self.client.get_item(
            TableName=self.table_name,
            Key={"article_id": {"S": article_id}},
            ProjectionExpression="article_id",
        )
        return "Item" not in response

    def mark_sent(self, article: Article) -> None:
        self._put_article(article, status="sent", sent_at=_now_iso())

    def mark_seeded(self, article: Article) -> None:
        self._put_article(article, status="seeded", sent_at="")

    def _put_article(self, article: Article, status: str, sent_at: str) -> None:
        item = {
            "article_id": {"S": article.article_id},
            "title": {"S": article.title},
            "link": {"S": article.link},
            "published": {"S": article.published},
            "status": {"S": status},
            "expire_at": {"N": str(_expire_at(self.ttl_days))},
        }
        if sent_at:
            item["sent_at"] = {"S": sent_at}
        self.client.put_item(TableName=self.table_name, Item=item)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _expire_at(ttl_days: int) -> int:
    return int((datetime.now(UTC) + timedelta(days=ttl_days)).timestamp())
