import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "vision_mock", True)  # no real call to Claude
    from app.main import app

    with TestClient(app) as c:
        yield c


def signup(client, username="alice", password="secret123"):
    r = client.post("/api/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def auth(client):
    return signup(client)


@pytest.fixture()
def jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), (120, 20, 40)).save(buf, format="JPEG")
    return buf.getvalue()
