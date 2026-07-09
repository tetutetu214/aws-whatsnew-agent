import json
from urllib import request

from src.line import (
    LINE_MESSAGES_PER_REQUEST,
    ArticleSummary,
    FlexMessage,
    build_flex_messages,
    build_short_id,
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


def test_記事ごとにFlexメッセージを作る() -> None:
    messages = build_flex_messages([_summary(1)])

    message = messages[0].message
    assert message["type"] == "flex"
    assert message["contents"]["type"] == "bubble"
    assert messages[0].article_ids == ("article-1",)


def test_short_idはarticle_idのSHA256先頭12桁になる() -> None:
    messages = build_flex_messages([_summary(1)])

    assert messages[0].short_id == build_short_id("article-1")
    assert len(messages[0].short_id) == 12


def test_いらないボタンはshort_idをpostback_dataに含める() -> None:
    messages = build_flex_messages([_summary(1)])

    footer = messages[0].message["contents"]["footer"]["contents"]
    dislike_button = footer[1]["action"]

    assert dislike_button["type"] == "postback"
    assert dislike_button["data"] == f"action=dislike&sid={messages[0].short_id}"


def test_グラフィカル解説ボタンはexplainのpostback_dataを持つ() -> None:
    messages = build_flex_messages([_summary(1)])

    footer = messages[0].message["contents"]["footer"]["contents"]
    explain_button = footer[2]["action"]

    assert explain_button["type"] == "postback"
    assert explain_button["label"] == "グラフィカル解説"
    assert explain_button["data"] == f"action=explain&sid={messages[0].short_id}"


def test_push送信は5メッセージごとにリクエストを分割する() -> None:
    chunks = [
        FlexMessage(
            message={"type": "text", "text": f"message {index}"},
            article_ids=(f"id-{index}",),
            short_id=f"short-{index}",
        )
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
