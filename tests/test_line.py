import json
from datetime import UTC, datetime
from urllib import request

from src.line import (
    LINE_MESSAGES_PER_REQUEST,
    ArticleSummary,
    MessageChunk,
    build_message_chunks,
    send_message_chunks,
)
from src.rss import Article


class FakeResponse:
    status = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class RecordingOpener:
    def __init__(self) -> None:
        self.requests: list[request.Request] = []

    def __call__(self, line_request: request.Request, timeout: int) -> FakeResponse:
        del timeout
        self.requests.append(line_request)
        return FakeResponse()


def test_11件の記事は既定10件ごとに2チャンクへ分割される() -> None:
    summaries = [_summary(index) for index in range(11)]

    chunks = build_message_chunks(
        summaries,
        max_articles_per_message=10,
        now=datetime(2026, 7, 6, tzinfo=UTC),
    )

    assert len(chunks) == 2
    assert len(chunks[0].article_ids) == 10
    assert len(chunks[1].article_ids) == 1


def test_5000文字を超える本文は複数チャンクへ分割される() -> None:
    summaries = [
        _summary(1, summary="a" * 3000),
        _summary(2, summary="b" * 3000),
    ]

    chunks = build_message_chunks(
        summaries,
        max_articles_per_message=10,
        now=datetime(2026, 7, 6, tzinfo=UTC),
    )

    assert len(chunks) == 2
    assert all(len(chunk.text) <= 5000 for chunk in chunks)


def test_push送信は5メッセージごとにリクエストを分割する() -> None:
    chunks = [
        MessageChunk(text=f"message {index}", article_ids=(f"id-{index}",))
        for index in range(LINE_MESSAGES_PER_REQUEST + 1)
    ]
    opener = RecordingOpener()

    sent_ids = send_message_chunks(
        "user-id",
        "channel-token",
        chunks,
        opener=opener,
    )

    assert len(opener.requests) == 2
    assert sent_ids == {f"id-{index}" for index in range(6)}
    first_payload = json.loads(opener.requests[0].data.decode("utf-8"))
    second_payload = json.loads(opener.requests[1].data.decode("utf-8"))
    assert len(first_payload["messages"]) == 5
    assert len(second_payload["messages"]) == 1


def _summary(index: int, summary: str | None = None) -> ArticleSummary:
    article_id = f"article-{index}"
    return ArticleSummary(
        article=Article(
            article_id=article_id,
            title=f"title {index}",
            link=f"https://example.com/{index}",
            description="description",
            published="Mon, 06 Jul 2026 00:00:00 GMT",
        ),
        summary=summary or f"summary {index}",
    )
