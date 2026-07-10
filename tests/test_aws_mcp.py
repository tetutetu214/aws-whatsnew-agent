"""AWS Knowledge MCP 富化のテスト。実 MCP には到達せず runner を注入して検証する。"""

from src import aws_mcp


def test_サービス名で検索し取得テキストを返す() -> None:
    calls: list[tuple[str, str]] = []

    def fake_runner(service_name: str, endpoint: str) -> str:
        calls.append((service_name, endpoint))
        return "BatchWriteRecordEntry: FeatureGroupName 必須, TtlDuration で自動削除"

    text = aws_mcp.fetch_service_context("Amazon SageMaker Feature Store", runner=fake_runner)

    assert "BatchWriteRecordEntry" in text
    assert calls[0][0] == "Amazon SageMaker Feature Store"


def test_サービス名が空なら検索せず空文字を返す() -> None:
    called: list[str] = []

    result = aws_mcp.fetch_service_context("", runner=lambda s, e: called.append(s) or "x")

    assert result == ""
    assert called == []


def test_MCP失敗時は空文字を返して富化なしで続行する() -> None:
    def failing_runner(service_name: str, endpoint: str) -> str:
        raise RuntimeError("mcp down")

    assert aws_mcp.fetch_service_context("Amazon S3", runner=failing_runner) == ""


def test_長すぎるコンテキストは上限で切り詰める() -> None:
    long_text = "あ" * 5000

    result = aws_mcp.fetch_service_context("svc", runner=lambda s, e: long_text)

    assert len(result) == aws_mcp.MAX_CONTEXT_CHARS
