import json
from pathlib import Path

import numpy as np

import embed
from embed import ArticleEmbedder


class DummyModel:
    def encode(self, texts, normalize_embeddings=True, show_progress_bar=True):
        return np.array([[float(i + 1), float(i + 2), float(i + 3)] for i, _ in enumerate(texts)])


def _write_article(path: Path, title: str, content: str, url: str) -> None:
    payload = {
        "title": title,
        "content": content,
        "url": url,
        "scraped_at": "2026-03-02 10:00:00",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_embedder_initialization_uses_model(monkeypatch, tmp_path):
    monkeypatch.setattr(embed, "SentenceTransformer", lambda *_args, **_kwargs: DummyModel())
    embedder = ArticleEmbedder(cache_dir=str(tmp_path / "embeddings"))

    assert embedder is not None
    assert hasattr(embedder, "model")
    assert embedder.model is not None


def test_embed_articles_generates_vectors_and_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(embed, "SentenceTransformer", lambda *_args, **_kwargs: DummyModel())

    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()
    _write_article(
        articles_dir / "first.txt",
        "First",
        "This is first article content. It has enough text for processing.",
        "https://example.com/first",
    )
    _write_article(
        articles_dir / "second.txt",
        "Second",
        "This is second article content. It also has enough text for processing.",
        "https://example.com/second",
    )

    embedder = ArticleEmbedder(cache_dir=str(tmp_path / "embeddings"), batch_size=2)
    out = embedder.embed_articles(str(articles_dir), force_update=True)

    assert len(out) == 2
    assert "first" in out
    assert "vector" in out["first"]
    assert len(out["first"]["vector"]) == 3
    assert out["first"]["metadata"]["title"] == "First"
    assert isinstance(out["first"]["cluster"], int)


def test_embed_articles_reuses_cache_when_no_new_articles(monkeypatch, tmp_path):
    monkeypatch.setattr(embed, "SentenceTransformer", lambda *_args, **_kwargs: DummyModel())

    embeddings_dir = tmp_path / "embeddings"
    embeddings_dir.mkdir()
    cache_file = embeddings_dir / "article_vectors.json"
    cache_file.write_text(
        json.dumps(
            {
                "cached": {
                    "vector": [1.0, 2.0, 3.0],
                    "cluster": 0,
                    "metadata": {"title": "Cached", "content": "x", "url": "u", "scraped_at": "2026-03-02 10:00:00"},
                }
            }
        ),
        encoding="utf-8",
    )

    articles_dir = tmp_path / "articles"
    articles_dir.mkdir()

    embedder = ArticleEmbedder(cache_dir=str(embeddings_dir))
    out = embedder.embed_articles(str(articles_dir), force_update=False)

    assert out["cached"]["metadata"]["title"] == "Cached"


def test_embed_articles_invalid_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(embed, "SentenceTransformer", lambda *_args, **_kwargs: DummyModel())
    embedder = ArticleEmbedder(cache_dir=str(tmp_path / "embeddings"))

    missing = tmp_path / "does_not_exist"
    try:
        embedder.embed_articles(str(missing))
        assert False, "Expected ValueError for missing directory"
    except ValueError as exc:
        assert "does not exist" in str(exc)
