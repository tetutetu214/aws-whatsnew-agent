"""Phase2 図解エージェントのテスト。

実 AWS（Bedrock/S3）・実 LINE に到達できない環境のため、これらはすべて fake を注入する。
"""

import json
from urllib import request

from src import explainer
from src.explainer import (
    ExplainerConfig,
    build_html,
    build_viewer_url,
    generate_explainer,
    store_html,
)


class FakeBedrock:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    def converse(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.text}]}}}


class FailingBedrock:
    def converse(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        raise RuntimeError("bedrock down")


class FakeS3:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)


class FakeStore:
    def __init__(self, mapping: dict[str, str] | None) -> None:
        self._mapping = mapping

    def get_feedback_mapping(self, short_id: str) -> dict[str, str] | None:
        del short_id
        return self._mapping


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


def _secrets(token_param: str, user_id_param: str) -> tuple[str, str]:
    del token_param, user_id_param
    return "channel-token", "user-id"


def _config() -> ExplainerConfig:
    return ExplainerConfig(
        bucket="bucket",
        model_id="model-x",
        viewer_base_url="https://viewer.example/",
    )


def _mapping() -> dict[str, str]:
    return {
        "article_id": "article-1",
        "title": "AWS Lambda MicroVMs",
        "category": "other",
        "link": "https://example.com/1",
        "description": "本文の説明",
    }


def test_build_htmlはモデルを指定して呼びHTMLを返す() -> None:
    bedrock = FakeBedrock("<html><body>図解</body></html>")

    html = build_html("題", "本文", "詳細", "model-x", bedrock)

    assert html == "<html><body>図解</body></html>"
    assert bedrock.calls[0]["modelId"] == "model-x"


def test_build_htmlはコードフェンスを剥がす() -> None:
    bedrock = FakeBedrock("```html\n<html>x</html>\n```")

    assert build_html("題", "本文", "", "model-x", bedrock) == "<html>x</html>"


def test_build_htmlは出典URLをプロンプトに渡す() -> None:
    # 図解フッターの出典リンクに使うため、記事の元URLをモデル入力に含める。
    bedrock = FakeBedrock("<html>x</html>")

    build_html("題", "本文", "", "model-x", bedrock, link="https://aws.amazon.com/whats-new/123")

    user_text = bedrock.calls[0]["messages"][0]["content"][0]["text"]
    assert "https://aws.amazon.com/whats-new/123" in user_text


def test_store_htmlはtext_htmlのContentTypeで指定バケットにputする() -> None:
    s3 = FakeS3()

    store_html("<html></html>", s3, "bucket", "explainer/a.html")

    assert s3.put_calls[0]["ContentType"] == "text/html; charset=utf-8"
    assert s3.put_calls[0]["Bucket"] == "bucket"
    assert s3.put_calls[0]["Key"] == "explainer/a.html"


def test_build_viewer_urlは閲覧LambdaのidつきURLを返す() -> None:
    # presigned は1600文字超で LINE の URI 上限を超えるため私有S3を返す閲覧Lambdaの短いURLを使う
    url = build_viewer_url("https://v.lambda-url.us-east-1.on.aws/", "abc123")

    assert url == "https://v.lambda-url.us-east-1.on.aws/?id=abc123"


def test_generate_explainerは図解を作りpresignedリンクをPushする() -> None:
    opener = RecordingOpener()
    bedrock = FakeBedrock("<html>図解</html>")
    s3 = FakeS3()

    result = generate_explainer(
        "abc123",
        FakeStore(_mapping()),
        _config(),
        bedrock_client=bedrock,
        s3_client=s3,
        opener=opener,
        secrets_loader=_secrets,
    )

    assert result["status"] == "sent"
    assert s3.put_calls[0]["Key"] == "explainer/abc123.html"
    pushed = json.loads(opener.requests[0].data.decode("utf-8"))
    button = pushed["messages"][0]["contents"]["footer"]["contents"][0]["action"]
    assert button["uri"] == "https://viewer.example/?id=abc123"


def test_generate_explainerはBedrock失敗時に失敗メッセージをPushする() -> None:
    opener = RecordingOpener()

    result = generate_explainer(
        "abc123",
        FakeStore(_mapping()),
        _config(),
        bedrock_client=FailingBedrock(),
        s3_client=FakeS3(),
        opener=opener,
        secrets_loader=_secrets,
    )

    assert result["status"] == "error"
    pushed = json.loads(opener.requests[0].data.decode("utf-8"))
    assert "失敗" in pushed["messages"][0]["text"]


def test_generate_explainerは対象記事が無ければ生成せず通知する() -> None:
    opener = RecordingOpener()
    bedrock = FakeBedrock("<html>x</html>")

    result = generate_explainer(
        "missing",
        FakeStore(None),
        _config(),
        bedrock_client=bedrock,
        s3_client=FakeS3(),
        opener=opener,
        secrets_loader=_secrets,
    )

    assert result["status"] == "not_found"
    assert bedrock.calls == []
    pushed = json.loads(opener.requests[0].data.decode("utf-8"))
    assert pushed["messages"][0]["text"] == "対象の記事が見つかりません"


def test_fetch_service_contextはmcp未注入なら空文字を返す() -> None:
    assert explainer.fetch_service_context("題", "https://x", None) == ""
