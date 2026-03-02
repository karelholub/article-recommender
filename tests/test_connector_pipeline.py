import json

from connector_pipeline import ConnectorIngestionService


class _MockResponse:
    def __init__(self, text="", content=b"", status_code=200):
        self.text = text
        self.content = content or text.encode("utf-8")
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def test_rss_connector_ingests_new_article(tmp_path, monkeypatch):
    embed_file = tmp_path / "article_vectors.json"
    embed_file.write_text("{}", encoding="utf-8")

    feed = """<?xml version="1.0"?>
<rss><channel>
  <item>
    <title>Test title</title>
    <link>https://news.example.com/a1</link>
    <description>Short summary</description>
    <pubDate>Mon, 01 Jan 2024 10:00:00 +0000</pubDate>
  </item>
</channel></rss>
"""
    article_html = """
<html><body>
  <h1>Test title</h1>
  <article><p>This is a test article body with enough words to pass validation for ingestion pipeline behavior and to ensure deterministic vector generation in tests.</p></article>
</body></html>
"""

    service = ConnectorIngestionService(embed_file)

    def _fake_get(url, timeout=12):  # noqa: ARG001
        if url.endswith("/feed.xml"):
            return _MockResponse(content=feed.encode("utf-8"))
        return _MockResponse(text=article_html)

    monkeypatch.setattr(service.session, "get", _fake_get)

    result = service.sync_connector(
        {
            "connector_id": "c1",
            "connector_type": "rss",
            "config": {"feed_url": "https://news.example.com/feed.xml"},
        }
    )
    assert result.ingested == 1
    assert result.attempted == 1

    stored = json.loads(embed_file.read_text(encoding="utf-8"))
    assert len(stored) == 1
    stored_item = next(iter(stored.values()))
    assert stored_item["metadata"]["url"] == "https://news.example.com/a1"
    assert isinstance(stored_item["vector"], list)
    assert len(stored_item["vector"]) == 64


def test_section_connector_skips_existing_url(tmp_path, monkeypatch):
    embed_file = tmp_path / "article_vectors.json"
    embed_file.write_text(
        json.dumps(
            {
                "existing": {
                        "vector": [1.0, 0.0],
                        "cluster": 0,
                        "metadata": {"url": "https://site.example.com/news/a1", "title": "Old", "content": "Old", "scraped_at": "2024-01-01 00:00:00"},
                    }
                }
            ),
            encoding="utf-8",
        )

    section_html = '<html><body><a href="/news/a1">A1</a></body></html>'
    article_html = """
<html><body>
  <h1>Same article</h1>
  <article><p>This article contains enough words and additional filler tokens to pass extraction while still being skipped because the URL already exists in cache records.</p></article>
</body></html>
"""

    service = ConnectorIngestionService(embed_file)

    def _fake_get(url, timeout=12):  # noqa: ARG001
        if url.endswith("/news"):
            return _MockResponse(text=section_html)
        return _MockResponse(text=article_html)

    monkeypatch.setattr(service.session, "get", _fake_get)

    result = service.sync_connector(
        {
            "connector_id": "c2",
            "connector_type": "section_scraper",
            "config": {"base_url": "https://site.example.com/news"},
        }
    )
    assert result.attempted == 1
    assert result.ingested == 0
    assert result.skipped_existing == 1
