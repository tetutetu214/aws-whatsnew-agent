from pathlib import Path

from src.rss import parse_articles


def test_guidがある記事はguidをarticle_idとして取り出す() -> None:
    xml_text = """
    <rss><channel>
      <item>
        <title>Amazon S3 update</title>
        <guid>guid-123</guid>
        <link>https://example.com/s3</link>
        <description><![CDATA[S3 description]]></description>
        <pubDate>Mon, 06 Jul 2026 00:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    articles = parse_articles(xml_text)

    assert len(articles) == 1
    assert articles[0].article_id == "guid-123"
    assert articles[0].title == "Amazon S3 update"
    assert articles[0].link == "https://example.com/s3"
    assert articles[0].description == "S3 description"
    assert articles[0].published == "Mon, 06 Jul 2026 00:00:00 GMT"


def test_descriptionのHTMLタグは除去されエンティティは復号される() -> None:
    xml_text = """
    <rss><channel>
      <item>
        <title>Amazon RDS update</title>
        <guid>guid-rds</guid>
        <link>https://example.com/rds</link>
        <description>&lt;p&gt;RDS is now &lt;b&gt;faster&lt;/b&gt; &amp; cheaper.&lt;/p&gt;</description>
        <pubDate>Mon, 06 Jul 2026 02:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    articles = parse_articles(xml_text)

    assert articles[0].description == "RDS is now faster & cheaper."


def test_guidがない記事はlinkをarticle_idとして取り出す() -> None:
    xml_text = """
    <rss><channel>
      <item>
        <title>Amazon EC2 update</title>
        <link>https://example.com/ec2</link>
        <description>EC2 &amp; compute</description>
        <pubDate>Mon, 06 Jul 2026 01:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """

    articles = parse_articles(xml_text)

    assert articles[0].article_id == "https://example.com/ec2"
    assert articles[0].description == "EC2 & compute"


def test_実フィードのDynamoDB記事には製品タグが含まれる() -> None:
    feed_path = Path(__file__).parent / "fixtures" / "whatsnew_feed_20261007.xml"
    articles = parse_articles(feed_path.read_text(encoding="utf-8"))

    article = next(
        article
        for article in articles
        if article.title == "Amazon DynamoDB introduces filtered export to Amazon S3"
    )

    assert "amazon-dynamodb" in article.categories


def test_categoryのない記事は空のタプルを返す() -> None:
    articles = parse_articles(
        "<rss><channel><item><title>更新</title><guid>no-tags</guid>"
        "</item></channel></rss>"
    )

    assert articles[0].categories == ()


def test_全categoryを製品名に正規化して重複を除き出現順を保つ() -> None:
    xml_text = """
    <rss><channel><item>
      <title>更新</title><guid>tags</guid>
      <category>
        general:products/AWS-Lambda,marketing:marchitecture/Databases
      </category>
      <category>general:products/aws-lambda,general:products/AMAZON-DYNAMODB</category>
      <category></category>
      <category>amazon-sqs, ,marketing:marchitecture/databases</category>
    </item></channel></rss>
    """

    articles = parse_articles(xml_text)

    assert articles[0].categories == (
        "aws-lambda",
        "databases",
        "amazon-dynamodb",
        "amazon-sqs",
    )
