from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib import parse, request
import base64
import hashlib
import hmac
import json
import logging
import re

try:
    from . import agent_trigger, filter_config, store
except ImportError:
    import agent_trigger
    import filter_config
    import store


LOGGER = logging.getLogger(__name__)
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"
DEFAULT_CHANNEL_SECRET_PARAM = "/whatsnew-agent/line/channel_secret"
DEFAULT_USER_ID_PARAM = "/whatsnew-agent/line/user_id"
DEFAULT_TOKEN_PARAM = "/whatsnew-agent/line/channel_token"
DEFAULT_MODEL_ID = "amazon.nova-micro-v1:0"


@dataclass(frozen=True)
class WebhookConfig:
    table_name: str
    line_token_param: str = DEFAULT_TOKEN_PARAM
    line_user_id_param: str = DEFAULT_USER_ID_PARAM
    line_channel_secret_param: str = DEFAULT_CHANNEL_SECRET_PARAM
    filter_config_param: str = filter_config.DEFAULT_FILTER_CONFIG_PARAM
    bedrock_model_id: str = DEFAULT_MODEL_ID
    ttl_days: int = 90


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    return handle_event(event)


def handle_event(
    event: dict[str, Any],
    app_config: WebhookConfig | None = None,
    ssm_client: Any | None = None,
    article_store: store.SentArticleStore | None = None,
    bedrock_client: Any | None = None,
    opener: Any | None = None,
    trigger: Any | None = None,
) -> dict[str, Any]:
    app_config = app_config or _load_webhook_config()
    ssm_client = ssm_client or _ssm_client()
    channel_secret = _get_parameter(
        ssm_client,
        app_config.line_channel_secret_param,
        with_decryption=True,
    )
    body_bytes = _body_bytes(event)
    signature = _header_value(event.get("headers", {}), "x-line-signature")
    if not signature or not verify_signature(body_bytes, signature, channel_secret):
        return {"statusCode": 403, "body": "Forbidden"}

    user_id = _get_parameter(
        ssm_client,
        app_config.line_user_id_param,
        with_decryption=True,
    )
    token = _get_parameter(
        ssm_client,
        app_config.line_token_param,
        with_decryption=True,
    )
    article_store = article_store or store.SentArticleStore(
        table_name=app_config.table_name,
        ttl_days=app_config.ttl_days,
    )
    payload = json.loads(body_bytes.decode("utf-8"))

    for line_event in payload.get("events", []):
        if line_event.get("source", {}).get("userId") != user_id:
            continue
        try:
            _handle_line_event(
                line_event,
                app_config,
                ssm_client,
                article_store,
                bedrock_client,
                token,
                opener,
                trigger,
            )
        except Exception as error:
            # 500 を返すと LINE が webhook を再送し、設定トグル等が
            # 二重適用されるためイベント単位で捕捉してログに残す
            LOGGER.warning(
                "Webhook event handling failed: %s",
                type(error).__name__,
            )

    return {"statusCode": 200, "body": "OK"}


def verify_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def _handle_line_event(
    line_event: dict[str, Any],
    app_config: WebhookConfig,
    ssm_client: Any,
    article_store: store.SentArticleStore,
    bedrock_client: Any | None,
    token: str,
    opener: Any | None,
    trigger: Any | None = None,
) -> None:
    reply_token = line_event.get("replyToken", "")
    if not reply_token:
        return

    if line_event.get("type") == "postback":
        _handle_postback(
            line_event.get("postback", {}).get("data", ""),
            reply_token,
            app_config,
            ssm_client,
            article_store,
            token,
            opener,
            trigger,
        )
        return

    if line_event.get("type") != "message":
        return
    message = line_event.get("message", {})
    if message.get("type") != "text":
        return
    text = str(message.get("text", "")).strip()
    if text == "設定":
        _reply(
            reply_token,
            token,
            [_settings_message(_load_filter_config(app_config, ssm_client))],
            opener,
        )
    elif text.startswith("除外追加 "):
        _add_category_from_text(
            text.removeprefix("除外追加 ").strip(),
            reply_token,
            app_config,
            ssm_client,
            bedrock_client,
            token,
            opener,
        )
    elif text == "カテゴリ削除":
        _reply(
            reply_token,
            token,
            [_delete_menu_message(_load_filter_config(app_config, ssm_client))],
            opener,
        )
    elif text == "集計":
        _reply(
            reply_token,
            token,
            [_text_message(_stats_text(article_store.scan_feedback_items()))],
            opener,
        )
    elif text == "提案":
        _reply(
            reply_token,
            token,
            [_suggestion_message(article_store, app_config, bedrock_client)],
            opener,
        )


def _handle_postback(
    data: str,
    reply_token: str,
    app_config: WebhookConfig,
    ssm_client: Any,
    article_store: store.SentArticleStore,
    token: str,
    opener: Any | None,
    trigger: Any | None = None,
) -> None:
    values = parse.parse_qs(data)
    action = _first(values, "action")
    if action == "explain":
        _handle_explain(
            _first(values, "sid"),
            reply_token,
            article_store,
            token,
            opener,
            trigger,
        )
        return
    if action == "toggle":
        category_id = _first(values, "id")
        current = _load_filter_config(app_config, ssm_client)
        updated = filter_config.toggle_category(current, category_id)
        filter_config.save_filter_config(
            updated,
            app_config.filter_config_param,
            ssm_client,
        )
        _reply(reply_token, token, [_settings_message(updated)], opener)
    elif action == "delete":
        category_id = _first(values, "id")
        current = _load_filter_config(app_config, ssm_client)
        updated = filter_config.delete_category(current, category_id)
        filter_config.save_filter_config(
            updated,
            app_config.filter_config_param,
            ssm_client,
        )
        _reply(reply_token, token, [_settings_message(updated)], opener)
    elif action == "dislike":
        _record_dislike(
            _first(values, "sid"),
            reply_token,
            article_store,
            token,
            opener,
        )
    elif action == "add":
        current = _load_filter_config(app_config, ssm_client)
        updated = filter_config.add_category(
            current,
            _first(values, "id"),
            _first(values, "label"),
            _first(values, "description"),
        )
        filter_config.save_filter_config(
            updated,
            app_config.filter_config_param,
            ssm_client,
        )
        _reply(reply_token, token, [_text_message("カテゴリを追加しました")], opener)


def _handle_explain(
    short_id: str,
    reply_token: str,
    article_store: store.SentArticleStore,
    token: str,
    opener: Any | None,
    trigger: Any | None,
) -> None:
    # 図解生成は数十秒かかるため webhook ではブロックしない。
    # 「生成中」を即 reply し、AgentCore Runtime を非同期起動して結果は後から Push。
    mapping = article_store.get_feedback_mapping(short_id)
    if not mapping:
        _reply(reply_token, token, [_text_message("対象の記事が見つかりません")], opener)
        return
    _reply(
        reply_token,
        token,
        [_text_message("🎨 図解を生成中です。少しお待ちください。")],
        opener,
    )
    invoke = trigger or agent_trigger.invoke_explainer
    invoke(short_id)


def _record_dislike(
    short_id: str,
    reply_token: str,
    article_store: store.SentArticleStore,
    token: str,
    opener: Any | None,
) -> None:
    mapping = article_store.get_feedback_mapping(short_id)
    if not mapping:
        _reply(reply_token, token, [_text_message("対象の記事が見つかりません")], opener)
        return
    article_store.mark_dislike(mapping["article_id"])
    _reply(
        reply_token,
        token,
        [_text_message(f"記録しました: {mapping['title']}")],
        opener,
    )


def _add_category_from_text(
    description: str,
    reply_token: str,
    app_config: WebhookConfig,
    ssm_client: Any,
    bedrock_client: Any | None,
    token: str,
    opener: Any | None,
) -> None:
    category = _generate_category(description, app_config.bedrock_model_id, bedrock_client)
    current = _load_filter_config(app_config, ssm_client)
    updated = filter_config.add_category(
        current,
        category["id"],
        category["label"],
        category["description"],
    )
    filter_config.save_filter_config(updated, app_config.filter_config_param, ssm_client)
    _reply(reply_token, token, [_text_message(f"追加しました: {category['label']}")], opener)


def _generate_category(
    description: str,
    model_id: str,
    bedrock_client: Any | None,
) -> dict[str, str]:
    if bedrock_client is None:
        import boto3

        bedrock_client = boto3.client("bedrock-runtime")
    try:
        response = bedrock_client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "次の除外カテゴリをJSONで返してください。"
                                "形式は{id,label,description}です。\n"
                                f"説明: {description}"
                            )
                        }
                    ],
                }
            ],
            inferenceConfig={"maxTokens": 120, "temperature": 0.2},
        )
        generated = json.loads(_extract_text(response))
        return {
            "id": _slug(generated.get("id") or generated.get("label") or description),
            "label": str(generated.get("label") or description)[:40],
            "description": str(generated.get("description") or description)[:200],
        }
    except Exception:
        return {
            "id": _slug(description),
            "label": description[:40],
            "description": description[:200],
        }


def _suggestion_message(
    article_store: store.SentArticleStore,
    app_config: WebhookConfig,
    bedrock_client: Any | None,
) -> dict[str, Any]:
    disliked = [
        item
        for item in article_store.scan_feedback_items()
        if item.get("feedback") == "dislike"
    ]
    if not disliked:
        return _text_message("まだデータがありません")

    suggestions = _generate_suggestions(
        [item.get("title", "") for item in disliked if item.get("title")],
        app_config.bedrock_model_id,
        bedrock_client,
    )
    if not suggestions:
        return _text_message("まだ提案できるカテゴリがありません")
    return _suggestion_buttons_message(suggestions)


def _generate_suggestions(
    titles: list[str],
    model_id: str,
    bedrock_client: Any | None,
) -> list[dict[str, str]]:
    if bedrock_client is None:
        import boto3

        bedrock_client = boto3.client("bedrock-runtime")
    try:
        response = bedrock_client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": (
                                "次の記事タイトル群から除外カテゴリ候補を最大3件、"
                                "JSON配列[{label,description}]で返してください。\n"
                                + "\n".join(titles[:80])
                            )
                        }
                    ],
                }
            ],
            inferenceConfig={"maxTokens": 300, "temperature": 0.4},
        )
        payload = json.loads(_extract_text(response))
    except Exception:
        return []

    suggestions: list[dict[str, str]] = []
    for item in payload[:3]:
        label = str(item.get("label", "")).strip()
        description = str(item.get("description", "")).strip()
        if label and description:
            suggestions.append(
                {
                    "id": _slug(label),
                    "label": label[:40],
                    "description": description[:160],
                }
            )
    return suggestions


def _settings_message(current: filter_config.FilterConfig) -> dict[str, Any]:
    text = "カテゴリ設定\n" + "\n".join(
        f"{'ON' if category.enabled else 'OFF'} {category.label} ({category.id})"
        for category in current.categories
    )
    # quickReply は最大13個。固定4ボタンを残すためカテゴリは9個まで
    quick_reply = [
        _postback_item(
            f"{category.label}: {'OFF' if category.enabled else 'ON'}",
            f"action=toggle&id={parse.quote(category.id)}",
        )
        for category in current.categories[:9]
    ]
    quick_reply.extend(
        [
            _message_item("集計", "集計"),
            _message_item("提案", "提案"),
            _message_item("カテゴリ削除", "カテゴリ削除"),
            _message_item("追加の使い方", "除外追加 <説明文>"),
        ]
    )
    return _text_message(text, quick_reply)


def _delete_menu_message(current: filter_config.FilterConfig) -> dict[str, Any]:
    categories = [category for category in current.categories if not category.builtin]
    if not categories:
        return _text_message("削除できるユーザー定義カテゴリはありません")
    return _text_message(
        "削除するカテゴリを選んでください",
        [
            _postback_item(
                category.label,
                f"action=delete&id={parse.quote(category.id)}",
            )
            for category in categories[:13]
        ],
    )


def _suggestion_buttons_message(suggestions: list[dict[str, str]]) -> dict[str, Any]:
    return _text_message(
        "カテゴリ候補",
        [
            _postback_item(
                suggestion["label"],
                parse.urlencode(
                    {
                        "action": "add",
                        "id": suggestion["id"],
                        "label": suggestion["label"],
                        "description": suggestion["description"],
                    }
                )[:300],
            )
            for suggestion in suggestions
        ],
    )


def _stats_text(items: list[dict[str, str]]) -> str:
    disliked = [item for item in items if item.get("feedback") == "dislike"]
    if not disliked:
        return "Not for Me 総数: 0"
    by_category = Counter(item.get("category", "unknown") for item in disliked)
    recent = sorted(
        disliked,
        key=lambda item: item.get("feedback_at", ""),
        reverse=True,
    )[:10]
    category_lines = "\n".join(
        f"- {category}: {count}件"
        for category, count in by_category.most_common()
    )
    recent_lines = "\n".join(
        f"- {item.get('title', '')}"
        for item in recent
    )
    return (
        f"Not for Me 総数: {len(disliked)}\n"
        f"カテゴリ別:\n{category_lines}\n"
        f"直近10件:\n{recent_lines}"
    )


def _reply(
    reply_token: str,
    channel_token: str,
    messages: list[dict[str, Any]],
    opener: Any | None,
) -> None:
    data = json.dumps(
        {
            "replyToken": reply_token,
            "messages": messages,
        }
    ).encode("utf-8")
    line_request = request.Request(
        LINE_REPLY_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {channel_token}",
        },
        method="POST",
    )
    request_opener = opener or request.urlopen
    with request_opener(line_request, timeout=20) as response:
        status_code = getattr(response, "status", 200)
        if status_code < 200 or status_code >= 300:
            raise RuntimeError(f"LINE reply failed: {status_code}")


def _text_message(
    text: str,
    quick_reply_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"type": "text", "text": text[:5000]}
    if quick_reply_items:
        message["quickReply"] = {"items": quick_reply_items[:13]}
    return message


def _postback_item(label: str, data: str) -> dict[str, Any]:
    return {
        "type": "action",
        "action": {
            "type": "postback",
            "label": label[:20],
            "data": data,
        },
    }


def _message_item(label: str, text: str) -> dict[str, Any]:
    return {
        "type": "action",
        "action": {
            "type": "message",
            "label": label[:20],
            "text": text,
        },
    }


def _load_filter_config(
    app_config: WebhookConfig,
    ssm_client: Any,
) -> filter_config.FilterConfig:
    return filter_config.load_filter_config(app_config.filter_config_param, ssm_client)


def _get_parameter(ssm_client: Any, name: str, with_decryption: bool) -> str:
    response = ssm_client.get_parameter(Name=name, WithDecryption=with_decryption)
    return response["Parameter"]["Value"]


def _body_bytes(event: dict[str, Any]) -> bytes:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode("utf-8")


def _header_value(headers: dict[str, str], key: str) -> str:
    for header_key, value in headers.items():
        if header_key.lower() == key:
            return value
    return ""


def _first(values: dict[str, list[str]], key: str) -> str:
    return values.get(key, [""])[0]


def _extract_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    texts = [
        item.get("text", "").strip()
        for item in content
        if isinstance(item, dict) and item.get("text")
    ]
    return "\n".join(texts).strip()


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if slug:
        return slug[:40]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"custom_{digest}"


def _ssm_client() -> Any:
    import boto3

    return boto3.client("ssm")


def _load_webhook_config() -> WebhookConfig:
    import os

    return WebhookConfig(
        table_name=os.environ.get("TABLE_NAME", "aws-whatsnew-agent-sent"),
        line_token_param=os.environ.get("LINE_TOKEN_PARAM", DEFAULT_TOKEN_PARAM),
        line_user_id_param=os.environ.get("LINE_USER_ID_PARAM", DEFAULT_USER_ID_PARAM),
        line_channel_secret_param=os.environ.get(
            "LINE_CHANNEL_SECRET_PARAM",
            DEFAULT_CHANNEL_SECRET_PARAM,
        ),
        filter_config_param=os.environ.get(
            "FILTER_CONFIG_PARAM",
            filter_config.DEFAULT_FILTER_CONFIG_PARAM,
        ),
        bedrock_model_id=os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID),
    )
