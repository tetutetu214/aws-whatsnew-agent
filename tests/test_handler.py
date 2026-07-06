from src.config import Config
from src.handler import run_pipeline
from src.line import MessageChunk
from src.rss import Article


class RecordingStore:
    def __init__(self, unsent_ids: set[str]) -> None:
        self.unsent_ids = unsent_ids
        self.seeded: list[str] = []
        self.sent: list[str] = []
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


def test_seed_mode_trueでは送信せずseeded記録だけ行う() -> None:
    store = RecordingStore({"article-1", "article-2"})
    send_calls: list[list[MessageChunk]] = []

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
        send_chunks_func=lambda user_id, token, chunks: {"article-1", "article-2"},
        ssm_client=FakeSsmClient(),
    )

    assert store.sent_summaries["article-1"] == "要約: title 1"
    assert store.sent_summaries["article-2"] == "要約: title 2"


class FakeSsmClient:
    def get_parameter(
        self,
        Name: str,
        WithDecryption: bool,
    ) -> dict[str, dict[str, str]]:
        del WithDecryption
        values = {
            "/token": "token-value",
            "/user": "user-value",
        }
        return {"Parameter": {"Value": values[Name]}}


def _config(seed_mode: bool) -> Config:
    return Config(
        table_name="table",
        bedrock_model_id="amazon.nova-micro-v1:0",
        line_token_param="/token",
        line_user_id_param="/user",
        seed_mode=seed_mode,
        exclude_services=(),
        rss_url="https://example.com/rss",
        max_articles_per_message=10,
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
