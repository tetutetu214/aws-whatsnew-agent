"""非同期トリガの契約テスト。

webhook が図解生成をブロックしないこと（dispatcher を InvocationType=Event で投げること）が
本設計の肝なので、その契約をここで固定する。実 AWS には到達しないため client を fake 注入する。
"""

import json

from src import agent_trigger


class FakeLambdaClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def invoke(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"StatusCode": 202}


class FakeAgentCoreClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def invoke_agent_runtime(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {}


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


def test_lambda_handlerはshort_idでAgentCoreを起動する() -> None:
    client = FakeAgentCoreClient()

    agent_trigger.invoke_agent_runtime(
        "abc123",
        runtime_arn="arn:runtime",
        client=client,
    )

    assert client.calls[0]["agentRuntimeArn"] == "arn:runtime"
    payload = json.loads(client.calls[0]["payload"].decode("utf-8"))
    assert payload == {"short_id": "abc123"}


def test_invoke_agent_runtimeはARN未設定なら何もしない() -> None:
    client = FakeAgentCoreClient()

    agent_trigger.invoke_agent_runtime("abc123", runtime_arn="", client=client)

    assert client.calls == []
