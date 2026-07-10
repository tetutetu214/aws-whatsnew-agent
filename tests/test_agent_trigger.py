"""非同期トリガの契約テスト。

webhook が図解生成をブロックしないこと（dispatcher を InvocationType=Event で投げること）と、
dispatcher が short_id で AgentCore Runtime を起動することを固定する。実 AWS には到達しない
ため client / invoke を fake 注入する。
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
    called: list[str] = []

    result = agent_trigger.lambda_handler(
        {"short_id": "abc123"},
        None,
        invoke=lambda sid: called.append(sid),
    )

    assert called == ["abc123"]
    assert result["status"] == "dispatched"


def test_lambda_handlerはshort_id無しなら起動しない() -> None:
    called: list[str] = []

    result = agent_trigger.lambda_handler(
        {},
        None,
        invoke=lambda sid: called.append(sid),
    )

    assert called == []
    assert result["status"] == "error"


def test_invoke_agent_runtimeはARNとshort_id付きで呼びセッションIDは33字以上() -> None:
    client = FakeAgentCoreClient()

    agent_trigger.invoke_agent_runtime("abc123", runtime_arn="arn:runtime", client=client)

    call = client.calls[0]
    assert call["agentRuntimeArn"] == "arn:runtime"
    assert len(call["runtimeSessionId"]) >= 33
    payload = json.loads(call["payload"].decode("utf-8"))
    assert payload == {"short_id": "abc123"}


def test_invoke_agent_runtimeはARN未設定なら何もしない() -> None:
    client = FakeAgentCoreClient()

    agent_trigger.invoke_agent_runtime("abc123", runtime_arn="", client=client)

    assert client.calls == []
