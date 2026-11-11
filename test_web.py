from types import SimpleNamespace

import pytest

from app import web_research
from app.config import settings
from app.vision import VisionError
from tests.conftest import signup


# ------------------------------------------------------------ API: sources, links, research

def test_sources_crud(client, auth):
    r = client.post("/api/sources", headers=auth, json={"url": "https://www.decanter.com", "label": "Decanter"})
    assert r.status_code == 201
    assert client.post("/api/sources", headers=auth, json={"url": "https://www.decanter.com"}).status_code == 409
    assert client.post("/api/sources", headers=auth, json={"url": "javascript:alert(1)"}).status_code == 422
    sources = client.get("/api/sources", headers=auth).json()
    assert [s["label"] for s in sources] == ["Decanter"]
    assert client.delete(f"/api/sources/{sources[0]['id']}", headers=auth).status_code == 204
    assert client.get("/api/sources", headers=auth).json() == []


def test_wine_links_and_research(client, auth):
    w = client.post("/api/wines", headers=auth, json={"name": "Clos de Vougeot", "producer": "Domaine Leroy",
                                                      "vintage": 2016}).json()
    links = client.post(f"/api/wines/{w['id']}/links", headers=auth,
                        json={"url": "https://example.com/fiche-technique", "label": "Fiche"}).json()
    assert [l["label"] for l in links] == ["Fiche"]

    r = client.post(f"/api/wines/{w['id']}/research", headers=auth)
    assert r.status_code == 200, r.text
    dossier = r.json()
    assert dossier["sources"] == [{"title": "Fiche", "url": "https://example.com/fiche-technique"}]
    assert dossier["vintage_description"]

    detail = client.get(f"/api/wines/{w['id']}", headers=auth).json()
    assert detail["dossier"]["wine_description"] == dossier["wine_description"]
    assert len(detail["links"]) == 1

    # Running it again updates the existing dossier (no duplicate)
    assert client.post(f"/api/wines/{w['id']}/research", headers=auth).status_code == 200

    client.delete(f"/api/wines/{w['id']}/links/{links[0]['id']}", headers=auth)
    assert client.get(f"/api/wines/{w['id']}", headers=auth).json()["links"] == []


def test_links_are_private(client, auth):
    w = client.post("/api/wines", headers=auth, json={"name": "Sancerre"}).json()
    other = signup(client, "dave")
    assert client.post(f"/api/wines/{w['id']}/links", headers=other,
                       json={"url": "https://example.com"}).status_code == 404
    assert client.post(f"/api/wines/{w['id']}/research", headers=other).status_code == 404


# ------------------------------------------------------------ research loop (simulated Claude)

DOSSIER_INPUT = {
    "wine_description": "Grand cru de la Côte de Nuits.",
    "tasting_profile": None,
    "producer_description": "Biodynamic estate in Vosne-Romanée.",
    "producer_website": "https://www.domaine-leroy.com",
    "region_description": "Côte de Nuits, Burgundy.",
    "vintage_description": "2016: spring frost, low yields, great purity.",
    "drinking_window": "2026-2050",
    "food_pairings": ["Pigeon rôti"],
    "critic_scores": [],
    "suggested_fields": {"producer": None, "appellation": "Clos de Vougeot Grand Cru", "region": "Burgundy",
                         "country": "France", "classification": "Grand Cru", "grapes": ["Pinot Noir"]},
    "sources": [{"title": "Domaine Leroy", "url": "https://www.domaine-leroy.com"}],
}


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _fake_client(monkeypatch, responses):
    messages = FakeMessages(responses)
    monkeypatch.setattr(settings, "vision_mock", False)
    monkeypatch.setattr(web_research, "_get_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    return messages


def _resp(stop_reason, *blocks):
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def test_research_loop_resumes_after_pause_then_saves(monkeypatch):
    save = SimpleNamespace(type="tool_use", name="save_wine_dossier", input=DOSSIER_INPUT, id="t1")
    msgs = _fake_client(monkeypatch, [
        _resp("pause_turn", SimpleNamespace(type="server_tool_use", name="web_search")),
        _resp("tool_use", save),
    ])
    links = [{"url": "https://example.com/fiche", "label": None}]
    d = web_research.research_wine({"name": "Clos de Vougeot", "vintage": 2016}, links, [])
    assert d.suggested_fields.grapes == ["Pinot Noir"]
    assert len(msgs.calls) == 2
    # The user's link is in the request (web_fetch only reads URLs present in the conversation)
    assert "https://example.com/fiche" in msgs.calls[0]["messages"][0]["content"]
    tool_types = {t.get("type", t.get("name")) for t in msgs.calls[0]["tools"]}
    assert {"web_fetch_20260209", "web_search_20260209", "save_wine_dossier"} <= tool_types


def test_research_refusal_raises(monkeypatch):
    _fake_client(monkeypatch, [_resp("refusal")])
    with pytest.raises(VisionError):
        web_research.research_wine({"name": "X"}, [], [])
