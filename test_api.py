from tests.conftest import signup


def _photos(jpeg, n=2):
    return [("photos", (f"p{i}.jpg", jpeg, "image/jpeg")) for i in range(n)]


def _add(client, auth, **wine):
    r = client.post("/api/wines", headers=auth, json=wine)
    assert r.status_code == 201, r.text
    return r.json()


def test_requires_auth(client):
    assert client.get("/api/wines").status_code == 401


def test_register_login_conflict(client):
    signup(client, "bob")
    assert client.post("/api/auth/register", json={"username": "BOB", "password": "secret123"}).status_code == 409
    assert client.post("/api/auth/login", json={"username": "bob", "password": "wrongpass"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "bob", "password": "secret123"}).status_code == 200


def test_scan_front_and_back_save_then_rescan(client, auth, jpeg_bytes):
    # 1. Scan front + back labels: new wine
    r = client.post("/api/scan", headers=auth, files=_photos(jpeg_bytes, 2))
    assert r.status_code == 200, r.text
    scan = r.json()
    assert len(scan["photo_ids"]) == 2
    assert scan["label"]["name"] == "Château Lynch-Bages"
    assert scan["label"]["vintage"] == 2016
    assert scan["already_tasted"]["same_vintage"] == []

    # 2. Save with both photos, a rating and notes
    body = {**scan["label"], "rating": 5, "notes": "Blackcurrant, cedar, very long.", "photo_ids": scan["photo_ids"]}
    for k in ("is_wine_label", "confidence"):
        body.pop(k)
    wine = _add(client, auth, **body)
    assert wine["photo_count"] == 2 and wine["rating"] == 5
    assert client.get(f"/api/wines/{wine['id']}/photos/0", headers=auth).status_code == 200
    assert client.get(f"/api/wines/{wine['id']}/photos/1", headers=auth).status_code == 200
    assert client.get(f"/api/wines/{wine['id']}/photos/2", headers=auth).status_code == 404

    # 3. New scan of the same bottle: recognised, with the notes
    same = client.post("/api/scan", headers=auth, files=_photos(jpeg_bytes, 1)).json()["already_tasted"]["same_vintage"]
    assert [w["id"] for w in same] == [wine["id"]]
    assert same[0]["notes"] == "Blackcurrant, cedar, very long."


def test_too_many_photos(client, auth, jpeg_bytes):
    assert client.post("/api/scan", headers=auth, files=_photos(jpeg_bytes, 5)).status_code == 400


def test_add_back_photo_later(client, auth, jpeg_bytes):
    w = _add(client, auth, name="Meursault")
    r = client.post(f"/api/wines/{w['id']}/photos", headers=auth, files=_photos(jpeg_bytes, 1))
    assert r.status_code == 201 and r.json()["photo_count"] == 1


def test_history_is_private_per_user(client, auth):
    _add(client, auth, name="Sancerre", color="white")
    other = signup(client, "carol")
    assert client.get("/api/wines", headers=other).json() == []
    wine_id = client.get("/api/wines", headers=auth).json()[0]["id"]
    assert client.get(f"/api/wines/{wine_id}", headers=other).status_code == 404


def _cellar(client, auth):
    _add(client, auth, name="Corton-Charlemagne", producer="Domaine Bonneau du Martray", vintage=2018,
         region="Burgundy", country="France", color="white")
    _add(client, auth, name="Clos de Vougeot", producer="Domaine Leroy", vintage=2016,
         region="burgundy", country="France", color="red")
    _add(client, auth, name="Château Lynch-Bages", vintage=2016, region="Bordeaux", appellation="Pauillac",
         country="France", color="red", grapes=["Cabernet Sauvignon"], rating=4)
    _add(client, auth, name="Château Pontet-Canet", vintage=2015, region="Bordeaux", appellation="Pauillac",
         country="France", color="red", grapes=["Cabernet Sauvignon"], rating=5)


def test_categories_group_by_producer_region_vintage(client, auth):
    _cellar(client, auth)
    cats = client.get("/api/categories", headers=auth).json()
    regions = {g["value"].lower(): g["count"] for g in cats["regions"]}
    assert regions == {"burgundy": 2, "bordeaux": 2}  # "Burgundy" and "burgundy" merged
    assert [g["value"] for g in cats["vintages"]] == [2018, 2016, 2015]
    assert {"value": 2016, "count": 2} in cats["vintages"]
    assert {g["value"] for g in cats["producers"]} >= {"Domaine Leroy", "Château Lynch-Bages"}


def test_filters_by_category(client, auth):
    _cellar(client, auth)
    get = lambda q: [w["name"] for w in client.get(f"/api/wines?{q}", headers=auth).json()]
    assert sorted(get("region=Burgundy")) == ["Clos de Vougeot", "Corton-Charlemagne"]
    assert sorted(get("vintage=2016")) == ["Château Lynch-Bages", "Clos de Vougeot"]
    assert get("producer=domaine leroy") == ["Clos de Vougeot"]
    assert get("region=Burgundy&color=white") == ["Corton-Charlemagne"]


def test_lookup_other_vintage_similar_and_same_year(client, auth):
    _cellar(client, auth)
    r = client.post("/api/lookup", headers=auth, json={
        "name": "Lynch Bages", "vintage": 2015, "color": "red", "appellation": "Pauillac",
        "region": "Bordeaux", "grapes": ["Cabernet Sauvignon"]}).json()
    assert r["already_tasted"]["same_vintage"] == []
    assert [w["vintage"] for w in r["already_tasted"]["other_vintages"]] == [2016]
    assert [w["name"] for w in r["similar"]] == ["Château Pontet-Canet"]
    assert [w["name"] for w in r["same_vintage_wines"]] == ["Château Pontet-Canet"]


def test_search_update_delete(client, auth):
    w = _add(client, auth, name="Côte-Rôtie", grapes=["Syrah"])
    assert len(client.get("/api/wines?q=syrah", headers=auth).json()) == 1
    assert len(client.get("/api/wines?q=cote rotie", headers=auth).json()) == 1
    r = client.patch(f"/api/wines/{w['id']}", headers=auth, json={"rating": 4, "notes": "Peppery"})
    assert r.json()["rating"] == 4
    assert client.delete(f"/api/wines/{w['id']}", headers=auth).status_code == 204
    assert client.get("/api/wines", headers=auth).json() == []


def test_bad_image_rejected(client, auth):
    r = client.post("/api/scan", headers=auth, files=[("photos", ("x.jpg", b"not an image", "image/jpeg"))])
    assert r.status_code == 422
