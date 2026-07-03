from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import request
import json
import logging

try:
    from .rss import Article
except ImportError:
    from rss import Article


LOGGER = logging.getLogger(__name__)
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_TEXT_LIMIT = 5000
LINE_MESSAGES_PER_REQUEST = 5


@dataclass(frozen=True)
class ArticleSummary:
    article: Article
    summary: str


@dataclass(frozen=True)
class MessageChunk:
    text: str
    article_ids: tuple[str, ...]


def build_message_chunks(
    article_summaries: list[ArticleSummary],
    max_articles_per_message: int = 10,
    now: datetime | None = None,
    text_limit: int = LINE_TEXT_LIMIT,
) -> list[MessageChunk]:
    if not article_summaries:
        return []

    current_now = now or datetime.now(UTC)
    date_text = current_now.astimezone().strftime("%Y-%m-%d")
    header = f"AWS What's New {date_text}: {len(article_summaries)}件"
    chunks: list[MessageChunk] = []
    current_lines = [header]
    current_ids: list[str] = []

    for item in article_summaries:
        entry = _format_entry(item)
        if len(entry) > text_limit - len(header) - 2:
            entry = entry[: text_limit - len(header) - 5] + "..."

        next_text = "\n\n".join([*current_lines, entry])
        should_split_by_count = len(current_ids) >= max_articles_per_message
        should_split_by_length = len(next_text) > text_limit

        if current_ids and (should_split_by_count or should_split_by_length):
            chunks.append(
                MessageChunk(
                    text="\n\n".join(current_lines),
                    article_ids=tuple(current_ids),
                )
            )
            current_lines = [header, entry]
            current_ids = [item.article.article_id]
            continue

        current_lines.append(entry)
        current_ids.append(item.article.article_id)

    if current_ids:
        chunks.append(
            MessageChunk(
                text="\n\n".join(current_lines),
                article_ids=tuple(current_ids),
            )
        )

    return chunks


def send_message_chunks(
    user_id: str,
    channel_token: str,
    chunks: list[MessageChunk],
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


def _format_entry(item: ArticleSummary) -> str:
    return f"• {item.summary}\n  詳細: {item.article.link}"


def _send_push_batch(
    user_id: str,
    channel_token: str,
    batch: list[MessageChunk],
    opener: Any,
) -> None:
    payload = {
        "to": user_id,
        "messages": [
            {"type": "text", "text": chunk.text[:LINE_TEXT_LIMIT]}
            for chunk in batch
        ],
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
