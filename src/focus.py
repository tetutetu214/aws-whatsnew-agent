import re

try:
    from .filter_config import Focus
    from .rss import Article
except ImportError:
    from filter_config import Focus
    from rss import Article


def is_in_focus(article: Article, focus: Focus) -> bool:
    if not focus.enabled:
        return True
    if any(category in focus.product_slugs for category in article.categories):
        return True
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", article.title, re.IGNORECASE)
        is not None
        for keyword in focus.title_keywords
        if keyword
    )
