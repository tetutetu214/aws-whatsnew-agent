from dataclasses import replace
from pathlib import Path

import pytest

from src.filter_config import DEFAULT_FOCUS
from src.focus import is_in_focus
from src.rss import Article, parse_articles


def test_実フィードの対象記事は指定の7件と完全一致する() -> None:
    articles = _feed_articles()

    matching_titles = {
        article.title for article in articles if is_in_focus(article, DEFAULT_FOCUS)
    }

    assert len(articles) == 100
    assert matching_titles == {
        (
            "Amazon ECS adds Amazon VPC Lattice support for blue/green, linear, "
            "and canary deployments"
        ),
        "Amazon DynamoDB introduces filtered export to Amazon S3",
        "Amazon DynamoDB Accelerator (DAX) is now available in additional Regions",
        "AgentCore Gateway supports private TLS certificates for VPC endpoints",
        (
            "Serverless Storage on Amazon EMR Serverless now supports "
            "terabyte-scale shuffle"
        ),
        (
            "Amazon Aurora serverless now scales faster to support agentic AI "
            "and other bursty workloads"
        ),
        "Amazon ElastiCache Serverless for Valkey now supports public endpoints",
    }


@pytest.mark.parametrize(
    "product_slug",
    [
        "aws-fargate",
        "amazon-simple-queue-service",
        "amazon-simple-notification-service",
    ],
)
def test_タイトルに対象語がなくても製品タグが一致する記事は通る(
    product_slug: str,
) -> None:
    article = _article("Amazon ECS deployment update", ("compute", product_slug))

    assert is_in_focus(article, DEFAULT_FOCUS) is True


@pytest.mark.parametrize(
    "title",
    [
        "New SERVERLESS storage",
        "AWS LAMBDA update",
        "Amazon API GATEWAY update",
        "AWS STEP FUNCTIONS update",
        "Amazon EVENTBRIDGE update",
        "Amazon DYNAMODB update",
        "Amazon SQS update",
        "Amazon SNS update",
        "AWS APPSYNC update",
        "AWS FARGATE update",
        "AWS AMPLIFY update",
        "AWS APP RUNNER update",
        "Amazon COGNITO update",
        "AGENTCORE Gateway update",
    ],
)
def test_タグがなくてもタイトル語は大文字小文字を区別せず通る(title: str) -> None:
    assert is_in_focus(_article(title), DEFAULT_FOCUS) is True


@pytest.mark.parametrize(
    "title",
    [
        "Transnational deployment update",
        "SNSignal update",
        "PreLambdaTest update",
        "Serverlessish deployment update",
        "Amazon API Gateways update",
    ],
)
def test_タイトル語が別の語の一部なら通らない(title: str) -> None:
    assert is_in_focus(_article(title), DEFAULT_FOCUS) is False


@pytest.mark.parametrize(
    ("title", "expected"),
    [("AWS lambda.v2 update", True), ("AWS lambdaXv2 update", False)],
)
def test_タイトル語の正規表現記号は文字どおりに判定する(
    title: str,
    expected: bool,
) -> None:
    focus = replace(DEFAULT_FOCUS, product_slugs=(), title_keywords=("lambda.v2",))

    assert is_in_focus(_article(title), focus) is expected


def test_focusが無効なら実フィードの全100件が通る() -> None:
    articles = _feed_articles()
    focus = replace(DEFAULT_FOCUS, enabled=False)

    assert len(articles) == 100
    assert all(is_in_focus(article, focus) for article in articles)


def test_製品タグの一部だけが一致する記事は通らない() -> None:
    article = _article("Amazon ECS deployment update", ("custom-aws-fargate",))

    assert is_in_focus(article, DEFAULT_FOCUS) is False


def test_空のタイトル語だけでは記事は通らない() -> None:
    focus = replace(DEFAULT_FOCUS, product_slugs=(), title_keywords=("",))

    assert is_in_focus(_article("Amazon EC2 update"), focus) is False


def _article(title: str, categories: tuple[str, ...] = ()) -> Article:
    return Article(
        article_id="article",
        title=title,
        link="https://example.com/article",
        description="更新内容",
        published="Wed, 07 Oct 2026 00:00:00 GMT",
        categories=categories,
    )


def _feed_articles() -> list[Article]:
    feed_path = Path(__file__).parent / "fixtures" / "whatsnew_feed_20261007.xml"
    return parse_articles(feed_path.read_text(encoding="utf-8"))
