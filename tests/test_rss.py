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
