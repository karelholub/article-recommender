import json

from recommend import AdvancedRecommender, RecommenderFactory


def _write_test_data(tmp_path):
    embeddings = {
        "article1": {
            "metadata": {
                "title": "Test Article 1",
                "content": "Content one",
                "url": "https://example.com/1",
                "scraped_at": "2026-03-02 10:00:00",
            },
            "cluster": 0,
            "vector": [0.1, 0.2, 0.3],
        },
        "article2": {
            "metadata": {
                "title": "Test Article 2",
                "content": "Content two",
                "url": "https://example.com/2",
                "scraped_at": "2026-03-01 10:00:00",
            },
            "cluster": 1,
            "vector": [0.4, 0.5, 0.6],
        },
        "article3": {
            "metadata": {
                "title": "Test Article 3",
                "content": "Content three",
                "url": "https://example.com/3",
                "scraped_at": "2026-02-27 10:00:00",
            },
            "cluster": 1,
            "vector": [0.2, 0.1, 0.4],
        },
    }
    profiles = {"test_user": ["article1"]}

    embed_file = tmp_path / "article_vectors.json"
    profile_file = tmp_path / "user_profiles.json"
    output_file = tmp_path / "recommendations.json"

    embed_file.write_text(json.dumps(embeddings), encoding="utf-8")
    profile_file.write_text(json.dumps(profiles), encoding="utf-8")

    return str(embed_file), str(profile_file), str(output_file)


def test_recommender_initialization(tmp_path):
    embed_file, profile_file, output_file = _write_test_data(tmp_path)

    recommender = AdvancedRecommender(
        embed_file=embed_file,
        profile_file=profile_file,
        output_file=output_file,
        diversity_weight=0.3,
        time_decay_days=30,
        cluster_weight=0.2,
    )

    assert recommender is not None
    assert recommender.diversity_weight == 0.3
    assert len(recommender.article_ids) == 3


def test_recommendations_generation(tmp_path):
    embed_file, profile_file, output_file = _write_test_data(tmp_path)

    recommender = RecommenderFactory.create_recommender(
        "advanced",
        embed_file=embed_file,
        profile_file=profile_file,
        output_file=output_file,
        diversity_weight=0.3,
        time_decay_days=30,
        cluster_weight=0.2,
    )

    recommendations = recommender.recommend_for_user(
        "test_user",
        recommender.article_vectors,
        ["article1"],
        top_n=2,
    )

    assert len(recommendations) == 2
    assert all(r["article_id"] != "article1" for r in recommendations)
    assert all("similarity_components" in r for r in recommendations)


def test_empty_user_reads_returns_empty_list(tmp_path):
    embed_file, profile_file, output_file = _write_test_data(tmp_path)

    recommender = AdvancedRecommender(
        embed_file=embed_file,
        profile_file=profile_file,
        output_file=output_file,
    )

    recommendations = recommender.recommend_for_user(
        "test_user",
        recommender.article_vectors,
        [],
        top_n=3,
    )

    assert recommendations == []


def test_factory_rejects_unknown_recommender():
    try:
        RecommenderFactory.create_recommender("does-not-exist")
        assert False, "Expected ValueError for unknown recommender"
    except ValueError as exc:
        assert "Unknown recommender type" in str(exc)
