from dataclasses import replace
from time import time
from unittest.mock import Mock
import json

import pytest

# 実 AWS・LINE API の呼び出しは禁止されているため、クライアントと送信処理を代替する。
from src.config import Config
from src.filter_config import DEFAULT_FILTER_CONFIG, DEFAULT_FOCUS, FilterConfig
from src.handler import run_pipeline
from src.line import FlexMessage
from src.rss import Article


class RecordingStore:
    def __init__(self, unsent_ids: set[str]) -> None:
        self.unsent_ids = unsent_ids
        self.seeded: list[str] = []
        self.sent: list[str] = []
        self.filtered: dict[str, str] = {}
        self.feedback_mappings: dict[str, str] = {}
        # article_id をキーに mark_sent へ渡された要約・モデルIDを記録する。
        self.sent_summaries: dict[str, str] = {}
        self.sent_model_ids: dict[str, str] = {}

    def is_unsent(self, article_id: str) -> bool:
        return article_id in self.unsent_ids

    def mark_seeded(self, article: Article) -> None:
        self.seeded.append(article.article_id)

    def mark_sent(self, article: Article, summary: str = "", model_id: str = "") -> None:
        self.sent.append(article.article_id)
        self.sent_summaries[article.article_id] = summary
        self.sent_model_ids[article.article_id] = model_id

    def mark_filtered(self, article: Article, category: str) -> None:
        self.filtered[article.article_id] = category

    def save_feedback_mapping(
        self,
        short_id: str,
        article: Article,
        category: str,
    ) -> None:
        del category
        self.feedback_mappings[short_id] = article.article_id


def test_seed_mode_trueでは送信せずseeded記録だけ行う() -> None:
    store = RecordingStore({"article-1", "article-2"})
    send_calls: list[list[FlexMessage]] = []

    result = run_pipeline(
        app_config=_config(seed_mode=True),
        article_store=store,
        fetch_articles_func=lambda url: _articles(),
        summarize_func=lambda article, model_id: article.title,
        send_chunks_func=lambda user_id, token, chunks: send_calls.append(chunks),
    )

    assert result["seeded"] == 2
    assert store.seeded == ["article-1", "article-2"]
    assert store.sent == []
    assert send_calls == []


def test_seed_mode_falseでは未送信の記事だけ送信済みに記録する() -> None:
    store = RecordingStore({"article-2"})

    result = run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=store,
        fetch_articles_func=lambda url: _articles(),
        summarize_func=lambda article, model_id: f"要約: {article.title}",
        classify_func=lambda article, config, model_id, bedrock_client=None: "other",
        send_chunks_func=lambda user_id, token, chunks: {"article-2"},
        ssm_client=FakeSsmClient(),
    )

    assert result["sent"] == 1
    assert store.seeded == []
    assert store.sent == ["article-2"]


def test_送信成功した記事にはその記事の要約とモデルIDが記録される() -> None:
    store = RecordingStore({"article-1", "article-2"})

    run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=store,
        fetch_articles_func=lambda url: _articles(),
        summarize_func=lambda article, model_id: f"要約: {article.title}",
        classify_func=lambda article, config, model_id, bedrock_client=None: "other",
        send_chunks_func=lambda user_id, token, chunks: {"article-2"},
        ssm_client=FakeSsmClient(),
    )

    assert store.sent_summaries["article-2"] == "要約: title 2"
    assert store.sent_model_ids["article-2"] == "amazon.nova-micro-v1:0"


def test_複数記事が送信成功しても要約が記事ごとに正しく対応する() -> None:
    store = RecordingStore({"article-1", "article-2"})

    run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=store,
        fetch_articles_func=lambda url: _articles(),
        summarize_func=lambda article, model_id: f"要約: {article.title}",
        classify_func=lambda article, config, model_id, bedrock_client=None: "other",
        send_chunks_func=lambda user_id, token, chunks: {"article-1", "article-2"},
        ssm_client=FakeSsmClient(),
    )

    assert store.sent_summaries["article-1"] == "要約: title 1"
    assert store.sent_summaries["article-2"] == "要約: title 2"


def test_分類で除外された記事は要約せずfiltered記録だけ行う() -> None:
    store = RecordingStore({"article-1", "article-2"})
    summarized: list[str] = []

    result = run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=store,
        fetch_articles_func=lambda url: _articles(),
        summarize_func=lambda article, model_id: _record_summary(article, summarized),
        classify_func=(
            lambda article, config, model_id, bedrock_client=None:
            "region_expansion" if article.article_id == "article-1" else "other"
        ),
        send_chunks_func=lambda user_id, token, chunks: {"article-2"},
        ssm_client=FakeSsmClient(),
    )

    assert result["filtered"] == 1
    assert store.filtered == {"article-1": "region_expansion"}
    assert summarized == ["article-2"]
    assert store.sent == ["article-2"]


def test_Flex送信時にfeedback対応レコードを保存する() -> None:
    store = RecordingStore({"article-2"})

    run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=store,
        fetch_articles_func=lambda url: _articles(),
        summarize_func=lambda article, model_id: f"要約: {article.title}",
        classify_func=lambda article, config, model_id, bedrock_client=None: "other",
        send_chunks_func=lambda user_id, token, chunks: {"article-2"},
        ssm_client=FakeSsmClient(),
    )

    assert list(store.feedback_mappings.values()) == ["article-2"]


class FakeSsmClient:
    def __init__(self, current_filter_config: FilterConfig | None = None) -> None:
        self.filter_config = current_filter_config or replace(
            DEFAULT_FILTER_CONFIG,
            focus=replace(DEFAULT_FOCUS, enabled=False),
        )

    def get_parameter(
        self,
        Name: str,
        WithDecryption: bool,
    ) -> dict[str, dict[str, str]]:
        del WithDecryption
        values = {
            "/token": "token-value",
            "/user": "user-value",
            "/filter": self.filter_config,
        }
        value = values[Name]
        if not isinstance(value, str):
            from src.filter_config import to_json

            value = to_json(value)
        return {"Parameter": {"Value": value}}


def _config(seed_mode: bool) -> Config:
    return Config(
        table_name="table",
        bedrock_model_id="amazon.nova-micro-v1:0",
        line_token_param="/token",
        line_user_id_param="/user",
        filter_config_param="/filter",
        seed_mode=seed_mode,
        rss_url="https://example.com/rss",
    )


def _articles() -> list[Article]:
    return [
        Article(
            article_id="article-1",
            title="title 1",
            link="https://example.com/1",
            description="description",
            published="Mon, 06 Jul 2026 00:00:00 GMT",
        ),
        Article(
            article_id="article-2",
            title="title 2",
            link="https://example.com/2",
            description="description",
            published="Mon, 06 Jul 2026 01:00:00 GMT",
        ),
    ]


def _record_summary(article: Article, summarized: list[str]) -> str:
    summarized.append(article.article_id)
    return f"要約: {article.title}"


def test_対象外の記事は分類も要約もせず対象外件数と記録に残す(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = RecordingStore({"article-1", "article-2"})
    classify_func = Mock()
    summarize_func = Mock()
    send_func = Mock()

    result = run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=store,
        fetch_articles_func=lambda url: _articles(),
        classify_func=classify_func,
        summarize_func=summarize_func,
        send_chunks_func=send_func,
        ssm_client=FakeSsmClient(DEFAULT_FILTER_CONFIG),
    )

    assert result == {
        "fetched": 2,
        "target": 2,
        "seeded": 0,
        "sent": 0,
        "filtered": 0,
        "out_of_focus": 2,
    }
    assert store.filtered == {
        "article-1": "out_of_focus",
        "article-2": "out_of_focus",
    }
    assert "Filtered as out_of_focus: title 1" in caplog.messages
    assert "Filtered as out_of_focus: title 2" in caplog.messages
    classify_func.assert_not_called()
    summarize_func.assert_not_called()
    send_func.assert_not_called()


def test_対象内のリージョン拡大記事は従来の除外件数に数える() -> None:
    article = replace(
        _articles()[0],
        title=(
            "Amazon DynamoDB Accelerator (DAX) is now available in additional Regions"
        ),
    )
    store = RecordingStore({article.article_id})
    summarize_func = Mock()
    bedrock_client = Mock()

    result = run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=store,
        fetch_articles_func=lambda url: [article],
        summarize_func=summarize_func,
        ssm_client=FakeSsmClient(DEFAULT_FILTER_CONFIG),
        bedrock_client=bedrock_client,
    )

    assert result == {
        "fetched": 1,
        "target": 1,
        "seeded": 0,
        "sent": 0,
        "filtered": 1,
        "out_of_focus": 0,
    }
    assert store.filtered == {article.article_id: "region_expansion"}
    summarize_func.assert_not_called()
    bedrock_client.converse.assert_not_called()


@pytest.mark.parametrize(
    ("scenario", "sent", "filtered", "out_of_focus"),
    [
        ("未送信なし", 0, 0, 0),
        ("対象外のみ", 0, 0, 1),
        ("分類で全件除外", 0, 1, 0),
        ("送信成功", 1, 0, 0),
        ("送信成功なし", 0, 0, 0),
    ],
)
def test_seed以外の全戻り経路で送信数のEMFを1行出す(
    scenario: str,
    sent: int,
    filtered: int,
    out_of_focus: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    article = _articles()[0]
    if scenario != "対象外のみ":
        article = replace(article, title="AWS Lambda update")
    store = RecordingStore(set() if scenario == "未送信なし" else {article.article_id})
    started_at = int(time() * 1000)

    result = run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=store,
        fetch_articles_func=lambda url: [article],
        summarize_func=lambda article, model_id: article.title,
        classify_func=Mock(return_value="region_expansion" if filtered else "other"),
        send_chunks_func=(
            lambda user_id, token, chunks: {article.article_id} if sent else set()
        ),
        ssm_client=FakeSsmClient(DEFAULT_FILTER_CONFIG),
    )

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    metric = json.loads(lines[0])
    assert metric["SentArticles"] == sent
    assert metric["_aws"]["CloudWatchMetrics"] == [
        {
            "Namespace": "AwsWhatsNewAgent",
            "Dimensions": [[]],
            "Metrics": [{"Name": "SentArticles", "Unit": "Count"}],
        }
    ]
    assert started_at <= metric["_aws"]["Timestamp"] <= int(time() * 1000)
    assert result == {
        "fetched": 1,
        "target": 0 if scenario == "未送信なし" else 1,
        "seeded": 0,
        "sent": sent,
        "filtered": filtered,
        "out_of_focus": out_of_focus,
    }


def test_seedモードでは設定の読み込みとEMF出力を行わない(
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = RecordingStore({"article-1", "article-2"})
    ssm_client = Mock()

    result = run_pipeline(
        app_config=_config(seed_mode=True),
        article_store=store,
        fetch_articles_func=lambda url: _articles(),
        ssm_client=ssm_client,
    )

    assert result == {"fetched": 2, "target": 2, "seeded": 2, "sent": 0}
    assert capsys.readouterr().out == ""
    ssm_client.get_parameter.assert_not_called()


def test_未送信記事がなければ設定を読み込まず対象外件数も0になる() -> None:
    ssm_client = Mock()

    result = run_pipeline(
        app_config=_config(seed_mode=False),
        article_store=RecordingStore(set()),
        fetch_articles_func=lambda url: _articles(),
        ssm_client=ssm_client,
    )

    assert result == {
        "fetched": 2,
        "target": 0,
        "seeded": 0,
        "sent": 0,
        "filtered": 0,
        "out_of_focus": 0,
    }
    ssm_client.get_parameter.assert_not_called()
