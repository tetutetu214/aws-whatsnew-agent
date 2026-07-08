from dataclasses import dataclass
from typing import Any
from urllib import request
import hashlib
import json
import logging

try:
    from .rss import Article
except ImportError:
    from rss import Article


LOGGER = logging.getLogger(__name__)
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_MESSAGES_PER_REQUEST = 5
SUMMARY_LIMIT = 700


@dataclass(frozen=True)
class ArticleSummary:
    article: Article
    summary: str
    category: str = "other"


@dataclass(frozen=True)
class FlexMessage:
    message: dict[str, Any]
    article_ids: tuple[str, ...]
    short_id: str


def build_flex_messages(
    article_summaries: list[ArticleSummary],
) -> list[FlexMessage]:
    return [_build_flex_message(item) for item in article_summaries]


def send_message_chunks(
    user_id: str,
    channel_token: str,
    chunks: list[FlexMessage],
    opener: Any | None = None,
) -> set[str]:
    sent_ids: set[str] = set()
    request_opener = opener or request.urlopen

    for index in range(0, len(chunks), LINE_MESSAGES_PER_REQUEST):
        batch = chunks[index : index + LINE_MESSAGES_PER_REQUEST]
        try:
            _send_push_batch(user_id, channel_token, batch, request_opener)
        except Exception as error:
            LOGGER.exception(
                "LINE push failed for message batch: %s",
                type(error).__name__,
            )
            continue

        for chunk in batch:
            sent_ids.update(chunk.article_ids)

    return sent_ids


def _send_push_batch(
    user_id: str,
    channel_token: str,
    batch: list[FlexMessage],
    opener: Any,
) -> None:
    payload = {
        "to": user_id,
        "messages": [chunk.message for chunk in batch],
    }
    data = json.dumps(payload).encode("utf-8")
    line_request = request.Request(
        LINE_PUSH_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_token}",
        },
        method="POST",
    )
    with opener(line_request, timeout=20) as response:
        status_code = getattr(response, "status", 200)
        if status_code < 200 or status_code >= 300:
            raise RuntimeError(f"LINE API returned status {status_code}")


def _build_flex_message(item: ArticleSummary) -> FlexMessage:
    short_id = build_short_id(item.article.article_id)
    message = {
        "type": "flex",
        "altText": _truncate(f"AWS What's New: {item.article.title}", 400),
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": item.article.title,
                        "weight": "bold",
                        "wrap": True,
                    },
                    {
                        "type": "text",
                        "text": _truncate(item.summary, SUMMARY_LIMIT),
                        "wrap": True,
                        "size": "sm",
                    },
                ],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "uri",
                            "label": "詳細",
                            "uri": item.article.link,
                        },
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "postback",
                            # 「いらない」はサービス自体の否定に読めるため
                            # 「自分には関係ない」の意の Not for Me にする（2026-07-08 てつてつ指定）
                            "label": "Not for Me",
                            "data": f"action=dislike&sid={short_id}",
                            "displayText": "Not for Me",
                        },
                    },
                ],
            },
        },
    }
    return FlexMessage(
        message=message,
        article_ids=(item.article.article_id,),
        short_id=short_id,
    )


def build_short_id(article_id: str) -> str:
    return hashlib.sha256(article_id.encode("utf-8")).hexdigest()[:12]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
