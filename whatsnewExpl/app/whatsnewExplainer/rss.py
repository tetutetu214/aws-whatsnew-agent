from dataclasses import dataclass
from html import unescape
from urllib.request import urlopen
import re
import xml.etree.ElementTree as ET


_TAG_RE = re.compile(r"<[^>]+>")


def _clean_description(raw: str) -> str:
    # RSS の description には <p> 等の HTML タグが含まれる。要約入力を汚さないよう
    # タグを除去し、エンティティを復号したうえで空白を整える。
    without_tags = _TAG_RE.sub(" ", raw)
    return " ".join(unescape(without_tags).split())


@dataclass(frozen=True)
class Article:
    article_id: str
    title: str
    link: str
    description: str
    published: str


def fetch_articles(
    rss_url: str,
    opener: object | None = None,
    timeout: int = 20,
) -> list[Article]:
    request_opener = opener or urlopen
    with request_opener(rss_url, timeout=timeout) as response:
        xml_text = response.read().decode("utf-8")
    return parse_articles(xml_text)


def parse_articles(xml_text: str) -> list[Article]:
    root = ET.fromstring(xml_text)
    articles: list[Article] = []

    for item in root.findall(".//item"):
        title = _text(item, "title")
        link = _text(item, "link")
        guid = _text(item, "guid")
        description = _text(item, "description")
        published = _text(item, "pubDate")
        article_id = guid or link

        if not article_id or not title:
            continue

        articles.append(
            Article(
                article_id=article_id,
                title=title,
                link=link,
                description=_clean_description(description),
                published=published,
            )
        )

    return articles


def _text(item: ET.Element, tag_name: str) -> str:
    child = item.find(tag_name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()
