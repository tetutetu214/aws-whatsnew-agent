import base64
import hashlib
import hmac
import json
from urllib import request

from src import filter_config
from src.webhook import WebhookConfig, handle_event


# 実 AWS・実 LINE 未認証環境のため SSM/DynamoDB/Reply API は fake で代替する。
class FakeSsmClient:
    def __init__(self) -> None:
        self.values = {
            "/secret": "channel-secret",
            "/user": "allowed-user",
            "/token": "channel-token",
            "/filter": filter_config.to_json(filter_config.DEFAULT_FILTER_CONFIG),
        }
        self.put_values: dict[str, str] = {}

    def get_parameter(
        self,
        Name: str,
        WithDecryption: bool,
    ) -> dict[str, dict[str, str]]:
        del WithDecryption
        return {"Parameter": {"Value": self.values[Name]}}

    def put_parameter(
        self,
        Name: str,
        Value: str,
        Type: str,
        Overwrite: bool,
    ) -> None:
        del Type, Overwrite
        self.values[Name] = Value
        self.put_values[Name] = Value


class FakeStore:
    def __init__(self) -> None:
        self.mapping = {
            "abc123": {
                "article_id": "article-1",
                "title": "対象記事",
                "category": "other",
            }
        }
        self.disliked: list[str] = []
        self.items: list[dict[str, str]] = []

    def get_feedback_mapping(self, short_id: str) -> dict[str, str] | None:
        return self.mapping.get(short_id)

    def mark_dislike(self, article_id: str) -> None:
        self.disliked.append(article_id)

    def scan_feedback_items(self) -> list[dict[str, str]]:
        return self.items


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


def test_署名が正しい時は200を返す() -> None:
    opener = RecordingOpener()

    response = handle_event(
        _event("設定"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=opener,
    )

    assert response["statusCode"] == 200
    assert len(opener.requests) == 1


def test_署名が偽の時は403を返す() -> None:
    response = handle_event(
        _event("設定", signature="invalid"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=RecordingOpener(),
    )

    assert response["statusCode"] == 403


def test_署名が欠落している時は403を返す() -> None:
    event = _event("設定")
    event["headers"] = {}

    response = handle_event(
        event,
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=RecordingOpener(),
    )

    assert response["statusCode"] == 403


def test_userIdが一致しないイベントは返信しない() -> None:
    opener = RecordingOpener()

    response = handle_event(
        _event("設定", user_id="other-user"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=opener,
    )

    assert response["statusCode"] == 200
    assert opener.requests == []


def test_設定コマンドはカテゴリ一覧を返信する() -> None:
    opener = RecordingOpener()

    handle_event(
        _event("設定"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=opener,
    )

    payload = _reply_payload(opener)
    assert "カテゴリ設定" in payload["messages"][0]["text"]
    assert "リージョン拡大" in payload["messages"][0]["text"]


def test_トグルpostbackはconfigを更新して返信する() -> None:
    opener = RecordingOpener()
    ssm_client = FakeSsmClient()

    handle_event(
        _postback_event("action=toggle&id=region_expansion"),
        app_config=_config(),
        ssm_client=ssm_client,
        article_store=FakeStore(),
        opener=opener,
    )

    updated = filter_config.parse_filter_config(ssm_client.put_values["/filter"])
    assert updated.categories[0].enabled is False
    assert len(opener.requests) == 1


def test_いらないpostbackはsent記事へdislikeを記録する() -> None:
    opener = RecordingOpener()
    article_store = FakeStore()

    handle_event(
        _postback_event("action=dislike&sid=abc123"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=article_store,
        opener=opener,
    )

    payload = _reply_payload(opener)
    assert article_store.disliked == ["article-1"]
    assert payload["messages"][0]["text"] == "記録しました: 対象記事"


def test_集計コマンドはいらない総数とカテゴリ別内訳を返信する() -> None:
    opener = RecordingOpener()
    article_store = FakeStore()
    article_store.items = [
        {
            "article_id": "article-1",
            "title": "記事1",
            "category": "region_expansion",
            "feedback": "dislike",
            "feedback_at": "2026-07-08T00:00:00+00:00",
        },
        {
            "article_id": "article-2",
            "title": "記事2",
            "category": "instance_size",
            "feedback": "dislike",
            "feedback_at": "2026-07-08T01:00:00+00:00",
        },
    ]

    handle_event(
        _event("集計"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=article_store,
        opener=opener,
    )

    text = _reply_payload(opener)["messages"][0]["text"]
    assert "Not for Me 総数: 2" in text
    assert "region_expansion: 1件" in text
    assert "記事2" in text


def test_提案コマンドはフィードバック0件ならデータなしを返信する() -> None:
    opener = RecordingOpener()

    handle_event(
        _event("提案"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=opener,
    )

    assert _reply_payload(opener)["messages"][0]["text"] == "まだデータがありません"


class RecordingTrigger:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, short_id: str) -> None:
        self.calls.append(short_id)


def test_グラフィカル解説postbackは生成中を返信し図解を非同期起動する() -> None:
    opener = RecordingOpener()
    trigger = RecordingTrigger()

    handle_event(
        _postback_event("action=explain&sid=abc123"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=opener,
        trigger=trigger,
    )

    assert "生成中" in _reply_payload(opener)["messages"][0]["text"]
    assert trigger.calls == ["abc123"]


def test_対象記事が無い解説postbackは起動せず見つからないを返す() -> None:
    opener = RecordingOpener()
    trigger = RecordingTrigger()

    handle_event(
        _postback_event("action=explain&sid=unknown"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=opener,
        trigger=trigger,
    )

    assert _reply_payload(opener)["messages"][0]["text"] == "対象の記事が見つかりません"
    assert trigger.calls == []


def _config() -> WebhookConfig:
    return WebhookConfig(
        table_name="table",
        line_token_param="/token",
        line_user_id_param="/user",
        line_channel_secret_param="/secret",
        filter_config_param="/filter",
    )


def _event(
    text: str,
    user_id: str = "allowed-user",
    signature: str | None = None,
) -> dict[str, object]:
    body = json.dumps(
        {
            "events": [
                {
                    "type": "message",
                    "replyToken": "reply-token",
                    "source": {"userId": user_id},
                    "message": {"type": "text", "text": text},
                }
            ]
        }
    )
    return _signed_event(body, signature)


def _postback_event(data: str) -> dict[str, object]:
    body = json.dumps(
        {
            "events": [
                {
                    "type": "postback",
                    "replyToken": "reply-token",
                    "source": {"userId": "allowed-user"},
                    "postback": {"data": data},
                }
            ]
        }
    )
    return _signed_event(body)


def _signed_event(body: str, signature: str | None = None) -> dict[str, object]:
    actual_signature = signature
    if actual_signature is None:
        digest = hmac.new(
            b"channel-secret",
            body.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        actual_signature = base64.b64encode(digest).decode("utf-8")
    return {
        "headers": {"x-line-signature": actual_signature},
        "body": body,
        "isBase64Encoded": False,
    }


class FailingOpener:
    def __call__(self, line_request: request.Request, timeout: int) -> FakeResponse:
        del line_request, timeout
        raise RuntimeError("reply failed")


def test_返信が失敗しても200を返してLINEの再送を防ぐ() -> None:
    # 500 を返すと LINE が webhook を再送し設定トグルが二重適用されるため
    response = handle_event(
        _event("設定"),
        app_config=_config(),
        ssm_client=FakeSsmClient(),
        article_store=FakeStore(),
        opener=FailingOpener(),
    )

    assert response["statusCode"] == 200


def _reply_payload(opener: RecordingOpener) -> dict[str, object]:
    return json.loads(opener.requests[0].data.decode("utf-8"))
