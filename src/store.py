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

    def mark_sent(self, article: Article, summary: str = "", model_id: str = "") -> None:
        self._put_article(
            article,
            status="sent",
            sent_at=_now_iso(),
            summary=summary,
            model_id=model_id,
        )

    def mark_seeded(self, article: Article) -> None:
        self._put_article(article, status="seeded", sent_at="")

    def mark_filtered(self, article: Article, category: str) -> None:
        self._put_article(
            article,
            status="filtered",
            sent_at="",
            category=category,
        )

    def save_feedback_mapping(
        self,
        short_id: str,
        article: Article,
        category: str,
    ) -> None:
        item = {
            "article_id": {"S": f"fb#{short_id}"},
            "article_ref": {"S": article.article_id},
            "title": {"S": article.title},
            "link": {"S": article.link},
            "category": {"S": category},
            "status": {"S": "feedback_mapping"},
            "expire_at": {"N": str(_expire_at(self.ttl_days))},
        }
        self.client.put_item(TableName=self.table_name, Item=item)

    def get_feedback_mapping(self, short_id: str) -> dict[str, str] | None:
        response = self.client.get_item(
            TableName=self.table_name,
            Key={"article_id": {"S": f"fb#{short_id}"}},
        )
        item = response.get("Item")
        if not item:
            return None
        return {
            "article_id": item.get("article_ref", {}).get("S", ""),
            "title": item.get("title", {}).get("S", ""),
            "category": item.get("category", {}).get("S", ""),
        }

    def mark_dislike(self, article_id: str) -> None:
        self.client.update_item(
            TableName=self.table_name,
            Key={"article_id": {"S": article_id}},
            UpdateExpression="SET feedback = :feedback, feedback_at = :feedback_at",
            ExpressionAttributeValues={
                ":feedback": {"S": "dislike"},
                ":feedback_at": {"S": _now_iso()},
            },
        )

    def scan_feedback_items(self) -> list[dict[str, str]]:
        # Scan は 1MB で打ち切られるため LastEvaluatedKey で全件を辿る
        items: list[dict[str, str]] = []
        scan_kwargs: dict[str, Any] = {"TableName": self.table_name}
        while True:
            response = self.client.scan(**scan_kwargs)
            items.extend(
                _from_ddb_item(item) for item in response.get("Items", [])
            )
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return items
            scan_kwargs["ExclusiveStartKey"] = last_key

    def _put_article(
        self,
        article: Article,
        status: str,
        sent_at: str,
        summary: str = "",
        model_id: str = "",
        category: str = "",
    ) -> None:
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
        # 空文字のときは属性自体を付けない（後からのモデル比較で無駄な空値を残さない）。
        if summary:
            item["summary"] = {"S": summary}
        if model_id:
            item["model_id"] = {"S": model_id}
        if category:
            item["category"] = {"S": category}
        self.client.put_item(TableName=self.table_name, Item=item)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _expire_at(ttl_days: int) -> int:
    return int((datetime.now(UTC) + timedelta(days=ttl_days)).timestamp())


def _from_ddb_item(item: dict[str, dict[str, str]]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in item.items():
        if "S" in value:
            values[key] = value["S"]
        elif "N" in value:
            values[key] = value["N"]
    return values
