from types import SimpleNamespace

import scrape
from scrape import ArticleScraper


class DummyResponse:
    def __init__(self, text, content_type="text/html"):
        self.text = text
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        return None


def test_scraper_initialization_without_network(monkeypatch):
    monkeypatch.setattr(ArticleScraper, "_init_session", lambda self: None)
    scraper = ArticleScraper()

    assert scraper is not None
    assert "User-Agent" in scraper.headers


def test_is_valid_article_url(monkeypatch):
    monkeypatch.setattr(ArticleScraper, "_init_session", lambda self: None)
    scraper = ArticleScraper()

    assert scraper._is_valid_article_url("https://www.e15.cz/geopolitika/some-article")
    assert not scraper._is_valid_article_url("https://example.com/x")
    assert not scraper._is_valid_article_url("https://www.e15.cz/facebook/something")


def test_get_article_links_parses_expected_urls(monkeypatch):
    monkeypatch.setattr(ArticleScraper, "_init_session", lambda self: None)
    monkeypatch.setattr(scrape.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scrape.random, "uniform", lambda *_args, **_kwargs: 0)

    html = """
    <html><body>
      <article class=\"article-item\"><a href=\"/geopolitika/a1\">a1</a></article>
      <div class=\"article-box\"><a href=\"https://www.e15.cz/geopolitika/a2\">a2</a></div>
      <div class=\"article-box\"><a href=\"/facebook/not-an-article\">bad</a></div>
    </body></html>
    """

    scraper = ArticleScraper()
    scraper.session.get = lambda *_args, **_kwargs: DummyResponse(html)

    links = scraper._get_article_links()

    assert len(links) == 2
    assert any(link.endswith("/geopolitika/a1") for link in links)
    assert any(link.endswith("/geopolitika/a2") for link in links)


def test_scrape_article_extracts_title_and_content(monkeypatch):
    monkeypatch.setattr(ArticleScraper, "_init_session", lambda self: None)
    monkeypatch.setattr(scrape.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scrape.random, "uniform", lambda *_args, **_kwargs: 0)

    long_text = " ".join(["word"] * 120)
    html = f"""
    <html><body>
      <h1>Example title</h1>
      <div class=\"article-content\"><p>{long_text}</p></div>
    </body></html>
    """

    scraper = ArticleScraper()
    scraper.session.get = lambda *_args, **_kwargs: DummyResponse(html)

    article = scraper._scrape_article("https://www.e15.cz/geopolitika/test")

    assert article is not None
    assert article["title"] == "Example title"
    assert article["url"].endswith("/test")
    assert len(article["content"].split()) >= 100


def test_scrape_and_save_writes_articles(monkeypatch, tmp_path):
    monkeypatch.setattr(ArticleScraper, "_init_session", lambda self: None)
    monkeypatch.setattr(scrape.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scrape.random, "uniform", lambda *_args, **_kwargs: 0)

    scraper = ArticleScraper()
    scraper.articles_dir = tmp_path / "articles"
    scraper.articles_dir.mkdir()

    scraper._get_article_links = lambda: ["https://www.e15.cz/geopolitika/a1"]
    scraper._scrape_article = lambda _url: {
        "title": "Sample title",
        "content": " ".join(["content"] * 110),
        "url": "https://www.e15.cz/geopolitika/a1",
        "scraped_at": "2026-03-02 10:00:00",
    }

    scraper.scrape_and_save(max_articles=1)

    saved = list(scraper.articles_dir.glob("*.txt"))
    assert len(saved) == 1
