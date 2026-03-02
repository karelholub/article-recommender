from meiro_adapter import MeiroAdapter


def test_normalize_profile_with_default_paths():
    adapter = MeiroAdapter(config={})
    profile = adapter.normalize_profile(
        {
            "external_id": "ext-1",
            "traits": {"preferred_sources": ["example.com"]},
            "segments": ["vip"],
        }
    )
    assert profile.external_user_id == "ext-1"
    assert profile.traits["preferred_sources"] == ["example.com"]
    assert profile.segments == ["vip"]


def test_normalize_profile_with_custom_paths():
    adapter = MeiroAdapter(config={})
    profile = adapter.normalize_profile(
        {
            "user": {"id": "ext-2"},
            "payload": {"attrs": {"a": 1}, "segments": "vip,high_value"},
        },
        mapping={
            "external_id_path": "user.id",
            "traits_path": "payload.attrs",
            "segments_path": "payload.segments",
        },
    )
    assert profile.external_user_id == "ext-2"
    assert profile.traits == {"a": 1}
    assert profile.segments == ["vip", "high_value"]
