from typing import Any
from time import time
import json
import logging

try:
    from . import classify, config, filter_config, focus, line, rss, store, summarize
except ImportError:
    import classify
    import config
    import filter_config
    import focus
    import line
    import rss
    import store
    import summarize


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
OUT_OF_FOCUS_CATEGORY = "out_of_focus"


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del event, context
    return run_pipeline()


def run_pipeline(
    app_config: config.Config | None = None,
    article_store: store.SentArticleStore | None = None,
    fetch_articles_func: Any | None = None,
    summarize_func: Any | None = None,
    send_chunks_func: Any | None = None,
    classify_func: Any | None = None,
    ssm_client: Any | None = None,
    bedrock_client: Any | None = None,
) -> dict[str, Any]:
    app_config = app_config or config.load_config()
    article_store = article_store or store.SentArticleStore(
        table_name=app_config.table_name,
        ttl_days=app_config.ttl_days,
    )
    fetch_articles_func = fetch_articles_func or rss.fetch_articles
    summarize_func = summarize_func or summarize.summarize_article
    send_chunks_func = send_chunks_func or line.send_message_chunks
    classify_func = classify_func or classify.classify_article

    articles = fetch_articles_func(app_config.rss_url)
    target_articles = [
        article
        for article in articles
        if article_store.is_unsent(article.article_id)
    ]
    LOGGER.info("Found %s unsent articles", len(target_articles))

    if app_config.seed_mode:
        for article in target_articles:
            article_store.mark_seeded(article)
        return {
            "fetched": len(articles),
            "target": len(target_articles),
            "seeded": len(target_articles),
            "sent": 0,
        }

    if not target_articles:
        _emit_sent_articles_metric(0)
        return {
            "fetched": len(articles),
            "target": 0,
            "seeded": 0,
            "sent": 0,
            "filtered": 0,
            "out_of_focus": 0,
        }

    current_filter_config = filter_config.load_filter_config(
        app_config.filter_config_param,
        ssm_client=ssm_client,
    )
    deliverable_articles: list[tuple[rss.Article, str]] = []
    filtered_count = 0
    out_of_focus_count = 0
    for article in target_articles:
        if not focus.is_in_focus(article, current_filter_config.focus):
            LOGGER.info("Filtered as %s: %s", OUT_OF_FOCUS_CATEGORY, article.title)
            article_store.mark_filtered(article, OUT_OF_FOCUS_CATEGORY)
            out_of_focus_count += 1
            continue
        category = classify_func(
            article,
            current_filter_config,
            app_config.bedrock_model_id,
            bedrock_client=bedrock_client,
        )
        if category != classify.OTHER_CATEGORY:
            # 除外はユーザーに見えないため、誤爆を後から監査できるようログに残す
            LOGGER.info("Filtered as %s: %s", category, article.title)
            article_store.mark_filtered(article, category)
            filtered_count += 1
            continue
        deliverable_articles.append((article, category))

    if not deliverable_articles:
        _emit_sent_articles_metric(0)
        return {
            "fetched": len(articles),
            "target": len(target_articles),
            "seeded": 0,
            "sent": 0,
            "filtered": filtered_count,
            "out_of_focus": out_of_focus_count,
        }

    article_summaries = [
        line.ArticleSummary(
            article=article,
            summary=summarize_func(article, app_config.bedrock_model_id),
            category=category,
        )
        for article, category in deliverable_articles
    ]
    chunks = line.build_flex_messages(article_summaries)
    for item in chunks:
        article = next(
            summary.article
            for summary in article_summaries
            if summary.article.article_id == item.article_ids[0]
        )
        article_store.save_feedback_mapping(item.short_id, article, "other")

    token, user_id = _load_line_secrets(
        app_config.line_token_param,
        app_config.line_user_id_param,
        ssm_client=ssm_client,
    )
    sent_article_ids = send_chunks_func(user_id, token, chunks)

    # article_id から対応する要約文を引くための対応表。記事と要約のズレを防ぐ。
    summary_by_article_id = {
        item.article.article_id: item.summary for item in article_summaries
    }

    sent_count = 0
    for article in target_articles:
        if article.article_id in sent_article_ids:
            article_store.mark_sent(
                article,
                summary=summary_by_article_id.get(article.article_id, ""),
                model_id=app_config.bedrock_model_id,
            )
            sent_count += 1

    _emit_sent_articles_metric(sent_count)
    return {
        "fetched": len(articles),
        "target": len(target_articles),
        "seeded": 0,
        "sent": sent_count,
        "filtered": filtered_count,
        "out_of_focus": out_of_focus_count,
    }


def _emit_sent_articles_metric(sent_count: int) -> None:
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "AwsWhatsNewAgent",
                            "Dimensions": [[]],
                            "Metrics": [{"Name": "SentArticles", "Unit": "Count"}],
                        }
                    ],
                },
                "SentArticles": sent_count,
            },
            separators=(",", ":"),
        )
    )


def _load_line_secrets(
    token_param: str,
    user_id_param: str,
    ssm_client: Any | None = None,
) -> tuple[str, str]:
    if ssm_client is None:
        import boto3

        ssm_client = boto3.client("ssm")

    token = _get_secure_parameter(ssm_client, token_param)
    user_id = _get_secure_parameter(ssm_client, user_id_param)
    return token, user_id


def _get_secure_parameter(ssm_client: Any, name: str) -> str:
    response = ssm_client.get_parameter(Name=name, WithDecryption=True)
    return response["Parameter"]["Value"]
