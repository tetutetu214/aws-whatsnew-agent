from typing import Any
import logging
import re

try:
    from .filter_config import Category, FilterConfig, enabled_categories
    from .rss import Article
except ImportError:
    from filter_config import Category, FilterConfig, enabled_categories
    from rss import Article


LOGGER = logging.getLogger(__name__)
OTHER_CATEGORY = "other"
SYSTEM_PROMPT = (
    "AWS What's Newの記事を、指定されたカテゴリidかotherのどれか1語だけで分類してください。"
)
BUILTIN_TITLE_RULES: dict[str, tuple[re.Pattern[str], ...]] = {
    "region_expansion": (
        # 「available ... Region(s)」を必須にする。単なる「in ... regions」だと
        # 機能追加の記事（例: ... on 26 additional EC2 instance types in all
        # commercial regions）まで誤爆するため（2026-07-08 実データで確認）
        re.compile(r"\bavailable\b.*\bregions?\b", re.IGNORECASE),
        re.compile(r"\badditional (aws )?regions?\b", re.IGNORECASE),
        re.compile(r"\bexpands? to\b.*\bregions?\b", re.IGNORECASE),
    ),
    "instance_size": (
        re.compile(r"\bnew .*instance (sizes?|types?)\b", re.IGNORECASE),
        re.compile(r"\b(adds?|introduces?) .*instance (sizes?|types?)\b", re.IGNORECASE),
        re.compile(r"\badditional .*instance (sizes?|types?)\b", re.IGNORECASE),
        re.compile(r"\b(graviton|ec2).*larger.*size", re.IGNORECASE),
    ),
}


def classify_article(
    article: Article,
    filter_config: FilterConfig,
    model_id: str,
    bedrock_client: Any | None = None,
) -> str:
    enabled = enabled_categories(filter_config)
    if not enabled:
        return OTHER_CATEGORY

    rule_category = _match_builtin_rule(article.title, enabled)
    if rule_category:
        return rule_category

    return _classify_by_llm(article, enabled, model_id, bedrock_client)


def _match_builtin_rule(title: str, categories: tuple[Category, ...]) -> str:
    enabled_ids = {category.id for category in categories}
    for category_id, patterns in BUILTIN_TITLE_RULES.items():
        if category_id not in enabled_ids:
            continue
        if any(pattern.search(title) for pattern in patterns):
            return category_id
    return ""


def _classify_by_llm(
    article: Article,
    categories: tuple[Category, ...],
    model_id: str,
    bedrock_client: Any | None,
) -> str:
    if bedrock_client is None:
        import boto3

        bedrock_client = boto3.client("bedrock-runtime")

    allowed_ids = {category.id for category in categories}
    category_lines = "\n".join(
        f"- {category.id}: {category.description}"
        for category in categories
    )
    prompt = (
        "次の記事を分類してください。\n"
        "候補カテゴリ:\n"
        f"{category_lines}\n"
        "- other: どのカテゴリにも当てはまらない重要な更新\n\n"
        f"タイトル: {article.title}\n"
        f"説明: {article.description}\n\n"
        "回答はカテゴリidまたはotherの1語のみ。"
    )

    try:
        response = bedrock_client.converse(
            modelId=model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            inferenceConfig={
                "maxTokens": 8,
                "temperature": 0,
            },
        )
    except Exception as error:
        LOGGER.warning(
            "Bedrock classify failed; using other: %s",
            type(error).__name__,
        )
        return OTHER_CATEGORY

    response_text = _extract_text(response)
    category_id = response_text.split()[0] if response_text else ""
    if category_id in allowed_ids:
        return category_id
    return OTHER_CATEGORY


def _extract_text(response: dict[str, Any]) -> str:
    content = response.get("output", {}).get("message", {}).get("content", [])
    texts = [
        item.get("text", "").strip()
        for item in content
        if isinstance(item, dict) and item.get("text")
    ]
    return " ".join(texts).strip()
