from meiro_adapter import MeiroAdapter


def test_request_url_template_used_for_fetch(monkeypatch):
    called = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "ok"}

    def fake_get(url, headers, timeout):
        called["url"] = url
        called["headers"] = headers
        called["timeout"] = timeout
        return DummyResponse()

    monkeypatch.setattr("requests.get", fake_get)
    adapter = MeiroAdapter(
        config={
            "request_url_template": "https://cdp.store.demo.meiro.io/wbs?segment=107&attribute=stitching_meiro_id&value={external_user_id}"
        }
    )
    payload = adapter.fetch_profile_payload("abc-123")
    assert payload["status"] == "ok"
    assert "value=abc-123" in called["url"]


def test_normalize_profile_with_default_paths():
    adapter = MeiroAdapter(config={})
    profile = adapter.normalize_profile(
        {
            "customer_entity_id": "ext-1",
            "returned_attributes": {"preferred_sources": ["example.com"]},
        }
    )
    assert profile.external_user_id == "ext-1"
    assert profile.traits["preferred_sources"] == ["example.com"]
    assert profile.segments == []


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
