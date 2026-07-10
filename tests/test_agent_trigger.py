"""非同期トリガの契約テスト。

webhook が図解生成をブロックしないこと（dispatcher を InvocationType=Event で投げること）と、
dispatcher が図解生成本体を short_id で実行することを固定する。実 AWS には到達しないため
client / generate を fake 注入する。
"""

import json

from src import agent_trigger


class FakeLambdaClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def invoke(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"StatusCode": 202}


def test_dispatch_asyncはEvent型でdispatcherを投げっぱなしにする() -> None:
    client = FakeLambdaClient()

    agent_trigger.dispatch_async("abc123", function_name="dispatcher-fn", client=client)

    assert client.calls[0]["InvocationType"] == "Event"
    assert client.calls[0]["FunctionName"] == "dispatcher-fn"
    payload = json.loads(client.calls[0]["Payload"].decode("utf-8"))
    assert payload == {"short_id": "abc123"}


def test_dispatch_asyncは関数名未設定なら何もしない() -> None:
    client = FakeLambdaClient()

    agent_trigger.dispatch_async("abc123", function_name="", client=client)

    assert client.calls == []


def test_lambda_handlerはshort_idで図解生成を実行する() -> None:
    called: list[str] = []

    result = agent_trigger.lambda_handler(
        {"short_id": "abc123"},
        None,
        generate=lambda sid: called.append(sid) or {"status": "sent"},
    )

    assert called == ["abc123"]
    assert result == {"status": "sent"}


def test_lambda_handlerはshort_id無しなら生成しない() -> None:
    called: list[str] = []

    result = agent_trigger.lambda_handler(
        {},
        None,
        generate=lambda sid: called.append(sid),
    )

    assert called == []
    assert result["status"] == "error"
