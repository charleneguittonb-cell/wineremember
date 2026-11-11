"""Wineremember API: photograph a bottle, keep a tasting history, find wines again."""
import json
import re
import shutil
import sqlite3
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import vision, web_research
from .auth import current_user, hash_password, issue_token, revoke_token, verify_password
from .config import settings
from .db import connect, init_db, wine_row_to_dict
from .matching import find_already_tasted, find_similar, match_key, normalize
from .schemas import Credentials, LinkIn, WineIn, WineUpdate

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
_PHOTO_ID = re.compile(r"^[0-9a-f]{32}$")
_WINE_SELECT = """SELECT w.*, (SELECT COUNT(*) FROM photos p WHERE p.wine_id = w.id) AS photo_count
                  FROM wines w"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Wineremember", version="1.1.0", lifespan=lifespan)


# ---------------------------------------------------------------- helpers

def _user_dir(user_id: int) -> Path:
    path = settings.uploads_dir / str(user_id)
    (path / "pending").mkdir(parents=True, exist_ok=True)
    return path


def _history(user_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            f"{_WINE_SELECT} WHERE w.user_id = ? ORDER BY COALESCE(w.tasted_on, w.created_at) DESC, w.id DESC",
            (user_id,),
        ).fetchall()
    return [wine_row_to_dict(r) for r in rows]


def _get_wine(user_id: int, wine_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(f"{_WINE_SELECT} WHERE w.id = ? AND w.user_id = ?", (wine_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wine not found")
    return wine_row_to_dict(row)


def _analyse(label: dict[str, Any], user_id: int, exclude_id: int | None = None) -> dict[str, Any]:
    """Already tasted? Other vintages? Similar wines? Other wines from the same vintage?"""
    history = [w for w in _history(user_id) if w["id"] != exclude_id]
    tasted = find_already_tasted(label, history)
    same_ids = {w["id"] for w in tasted["same_vintage"] + tasted["other_vintages"]}
    vintage = label.get("vintage")
    same_year = [w for w in history if vintage and w.get("vintage") == vintage and w["id"] not in same_ids]
    same_year.sort(key=lambda w: -(w.get("rating") or 0))
    return {
        "already_tasted": tasted,
        "similar": find_similar(label, history, exclude_ids=same_ids),
        "same_vintage_wines": same_year[:10],
    }


async def _read_uploads(photos: list[UploadFile]) -> list[bytes]:
    if not photos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No photo received")
    if len(photos) > settings.max_photos_per_wine:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{settings.max_photos_per_wine} photos maximum per bottle")
    jpegs = []
    for photo in photos:
        raw = await photo.read(settings.max_upload_bytes + 1)
        if len(raw) > settings.max_upload_bytes:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Photo too large")
        try:
            jpegs.append(await run_in_threadpool(vision.prepare_image, raw))
        except vision.VisionError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return jpegs


def _attach_photos(conn: sqlite3.Connection, user_id: int, wine_id: int, files: list[str], start: int) -> None:
    conn.executemany(
        "INSERT INTO photos (wine_id, file, position) VALUES (?, ?, ?)",
        [(wine_id, f"{user_id}/{name}", start + i) for i, name in enumerate(files)],
    )


# ---------------------------------------------------------------- auth

@app.post("/api/auth/register", status_code=201)
def register(body: Credentials):
    try:
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (body.username.strip(), hash_password(body.password)),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "This username is already taken")
    return {"token": issue_token(user_id), "username": body.username.strip()}


@app.post("/api/auth/login")
def login(body: Credentials):
    with connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (body.username.strip(),)
        ).fetchone()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    return {"token": issue_token(row["id"]), "username": row["username"]}


@app.post("/api/auth/logout", status_code=204)
def logout(user: dict = Depends(current_user)):
    revoke_token(user["token"])


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    with connect() as conn:
        stats = conn.execute(
            """SELECT COUNT(*) AS total, ROUND(AVG(rating), 1) AS avg_rating,
                      COUNT(DISTINCT region) AS regions, COUNT(DISTINCT producer) AS producers
               FROM wines WHERE user_id = ?""",
            (user["id"],),
        ).fetchone()
    return {"username": user["username"], "stats": dict(stats)}


# ---------------------------------------------------------------- scan

@app.post("/api/scan")
async def scan(photos: list[UploadFile] = File(...), user: dict = Depends(current_user)):
    """Analyse 1 to 4 photos of the same bottle (front label first, then back label).

    Nothing is saved to the history here: the photos stay pending
    and `photo_ids` attaches them on POST /api/wines.
    """
    jpegs = await _read_uploads(photos)
    try:
        label = await run_in_threadpool(vision.read_label, jpegs)
    except vision.VisionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    photo_ids = []
    for jpeg in jpegs:
        pid = uuid.uuid4().hex
        (_user_dir(user["id"]) / "pending" / f"{pid}.jpg").write_bytes(jpeg)
        photo_ids.append(pid)

    label_dict = label.model_dump()
    result: dict[str, Any] = {"photo_ids": photo_ids, "label": label_dict}
    if label.is_wine_label:
        result.update(_analyse(label_dict, user["id"]))
    else:
        result.update({"already_tasted": {"same_vintage": [], "other_vintages": []},
                       "similar": [], "same_vintage_wines": []})
    return result


@app.post("/api/lookup")
def lookup(body: WineUpdate, user: dict = Depends(current_user)):
    """Same lookup as /api/scan, but from fields typed or corrected by hand."""
    label = body.model_dump()
    label["grapes"] = label.get("grapes") or []
    return _analyse(label, user["id"])


@app.post("/api/suggestions")
async def suggestions(body: WineUpdate, user: dict = Depends(current_user)):
    """Similar wines outside the history, suggested by Claude based on the user's tastes."""
    history = _history(user["id"])
    liked = [w for w in history if (w.get("rating") or 0) >= 4][:15]
    tasted = sorted({f"{w.get('producer') or ''} {w['name']}".strip() for w in history})[:100]
    try:
        result = await run_in_threadpool(vision.suggest_similar, body.model_dump(), liked, tasted)
    except vision.VisionError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return result.model_dump()


# ---------------------------------------------------------------- categories

def _producer_of(w: dict[str, Any]) -> str:
    return w.get("producer") or w["name"]


@app.get("/api/categories")
def categories(user: dict = Depends(current_user)):
    """History grouped by producer, region, vintage, appellation, country and color (with counts)."""
    history = _history(user["id"])

    def group(values) -> list[dict[str, Any]]:
        # Merge spelling variants ("Burgundy" / "burgundy") under the most frequent form.
        by_norm: dict[str, Counter] = {}
        for v in values:
            if v in (None, ""):
                continue
            by_norm.setdefault(normalize(str(v)), Counter())[v] += 1
        groups = [{"value": c.most_common(1)[0][0], "count": sum(c.values())} for c in by_norm.values()]
        return sorted(groups, key=lambda g: (-g["count"], str(g["value"]).lower()))

    vintages = sorted(group(w.get("vintage") for w in history), key=lambda g: -g["value"])
    return {
        "producers": group(_producer_of(w) for w in history),
        "regions": group(w.get("region") for w in history),
        "appellations": group(w.get("appellation") for w in history),
        "vintages": vintages,
        "countries": group(w.get("country") for w in history),
        "colors": group(w.get("color") for w in history),
    }


# ---------------------------------------------------------------- history

@app.get("/api/wines")
def list_wines(
    q: str | None = Query(default=None, max_length=100),
    producer: str | None = None,
    region: str | None = None,
    appellation: str | None = None,
    country: str | None = None,
    vintage: int | None = None,
    color: str | None = None,
    min_rating: int | None = Query(default=None, ge=1, le=5),
    sort: str = Query(default="recent", pattern="^(recent|rating|vintage|name)$"),
    user: dict = Depends(current_user),
):
    wines = _history(user["id"])
    if q:
        needle = normalize(q)
        fields = ("name", "producer", "appellation", "region", "country", "vintage", "notes", "occasion")
        wines = [
            w for w in wines
            if needle in normalize(" ".join(str(w.get(f) or "") for f in fields) + " " + " ".join(w["grapes"]))
        ]
    # Exact category filters (case- and accent-insensitive)
    for field, value in (("region", region), ("appellation", appellation), ("country", country), ("color", color)):
        if value:
            wines = [w for w in wines if normalize(w.get(field)) == normalize(value)]
    if producer:
        wines = [w for w in wines if normalize(_producer_of(w)) == normalize(producer)]
    if vintage:
        wines = [w for w in wines if w.get("vintage") == vintage]
    if min_rating:
        wines = [w for w in wines if (w.get("rating") or 0) >= min_rating]
    if sort == "rating":
        wines.sort(key=lambda w: -(w.get("rating") or 0))
    elif sort == "vintage":
        wines.sort(key=lambda w: -(w.get("vintage") or 0))
    elif sort == "name":
        wines.sort(key=lambda w: _producer_of(w).lower())
    return wines


@app.post("/api/wines", status_code=201)
def create_wine(body: WineIn, user: dict = Depends(current_user)):
    udir = _user_dir(user["id"])
    for pid in body.photo_ids:
        if not _PHOTO_ID.match(pid):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid photo_id")
        if not (udir / "pending" / f"{pid}.jpg").exists():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Photo expired, please scan the bottle again")

    data = body.model_dump(exclude={"photo_ids"})
    data["grapes"] = json.dumps([g.strip() for g in data["grapes"] if g.strip()], ensure_ascii=False)
    files = []
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO wines (user_id, name, producer, vintage, appellation, region, country, color,
                                  grapes, classification, rating, notes, tasted_on, occasion, match_key)
               VALUES (:user_id, :name, :producer, :vintage, :appellation, :region, :country, :color,
                       :grapes, :classification, :rating, :notes, :tasted_on, :occasion, :match_key)""",
            {**data, "user_id": user["id"], "match_key": match_key(body.name, body.producer)},
        )
        wine_id = cur.lastrowid
        for pid in body.photo_ids:
            shutil.move(udir / "pending" / f"{pid}.jpg", udir / f"{pid}.jpg")
            files.append(f"{pid}.jpg")
        _attach_photos(conn, user["id"], wine_id, files, start=0)
    return _get_wine(user["id"], wine_id)


def _links(wine_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT id, url, label FROM wine_links WHERE wine_id = ? ORDER BY id", (wine_id,))
        return [dict(r) for r in rows]


def _sources(user_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT id, url, label FROM sources WHERE user_id = ? ORDER BY id", (user_id,))
        return [dict(r) for r in rows]


def _dossier(wine_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT data, updated_at FROM dossiers WHERE wine_id = ?", (wine_id,)).fetchone()
    return {**json.loads(row["data"]), "updated_at": row["updated_at"]} if row else None


@app.get("/api/wines/{wine_id}")
def get_wine(wine_id: int, user: dict = Depends(current_user)):
    wine = _get_wine(user["id"], wine_id)
    return {**wine, **_analyse(wine, user["id"], exclude_id=wine_id),
            "links": _links(wine_id), "dossier": _dossier(wine_id)}


@app.patch("/api/wines/{wine_id}")
def update_wine(wine_id: int, body: WineUpdate, user: dict = Depends(current_user)):
    current = _get_wine(user["id"], wine_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and not changes["name"]:
        del changes["name"]  # the name is required
    if not changes:
        return current
    merged = {**current, **changes}
    if "grapes" in changes:
        changes["grapes"] = json.dumps(changes["grapes"] or [], ensure_ascii=False)
    changes["match_key"] = match_key(merged["name"], merged.get("producer"))
    sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys come from the pydantic schema only
    with connect() as conn:
        conn.execute(f"UPDATE wines SET {sets} WHERE id = :id AND user_id = :uid",
                     {**changes, "id": wine_id, "uid": user["id"]})
    return _get_wine(user["id"], wine_id)


@app.delete("/api/wines/{wine_id}", status_code=204)
def delete_wine(wine_id: int, user: dict = Depends(current_user)):
    _get_wine(user["id"], wine_id)
    with connect() as conn:
        files = [r["file"] for r in conn.execute("SELECT file FROM photos WHERE wine_id = ?", (wine_id,))]
        conn.execute("DELETE FROM wines WHERE id = ? AND user_id = ?", (wine_id, user["id"]))
    for f in files:
        (settings.uploads_dir / f).unlink(missing_ok=True)


# ---------------------------------------------------------------- links and web research

@app.get("/api/sources")
def list_sources(user: dict = Depends(current_user)):
    """The user's reference sites, consulted on every research."""
    return _sources(user["id"])


@app.post("/api/sources", status_code=201)
def add_source(body: LinkIn, user: dict = Depends(current_user)):
    try:
        with connect() as conn:
            cur = conn.execute("INSERT INTO sources (user_id, url, label) VALUES (?, ?, ?)",
                               (user["id"], body.url.strip(), body.label))
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "This site is already in your sources")
    return {"id": cur.lastrowid, "url": body.url.strip(), "label": body.label}


@app.delete("/api/sources/{source_id}", status_code=204)
def delete_source(source_id: int, user: dict = Depends(current_user)):
    with connect() as conn:
        conn.execute("DELETE FROM sources WHERE id = ? AND user_id = ?", (source_id, user["id"]))


@app.post("/api/wines/{wine_id}/links", status_code=201)
def add_link(wine_id: int, body: LinkIn, user: dict = Depends(current_user)):
    """Attach a link to a wine (technical sheet, estate page, press article...)."""
    _get_wine(user["id"], wine_id)
    with connect() as conn:
        conn.execute("INSERT INTO wine_links (wine_id, url, label) VALUES (?, ?, ?)",
                     (wine_id, body.url.strip(), body.label))
    return _links(wine_id)


@app.delete("/api/wines/{wine_id}/links/{link_id}", status_code=204)
def delete_link(wine_id: int, link_id: int, user: dict = Depends(current_user)):
    _get_wine(user["id"], wine_id)
    with connect() as conn:
        conn.execute("DELETE FROM wine_links WHERE id = ? AND wine_id = ?", (link_id, wine_id))


@app.post("/api/wines/{wine_id}/research")
async def research(wine_id: int, user: dict = Depends(current_user)):
    """Research the web (wine links, user sources, then the open web) and save the dossier."""
    wine = _get_wine(user["id"], wine_id)
    try:
        dossier = await run_in_threadpool(
            web_research.research_wine, wine, _links(wine_id), _sources(user["id"]))
    except vision.VisionError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    with connect() as conn:
        conn.execute(
            """INSERT INTO dossiers (wine_id, data, updated_at) VALUES (?, ?, datetime('now'))
               ON CONFLICT(wine_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at""",
            (wine_id, dossier.model_dump_json()),
        )
    return _dossier(wine_id)


# ---------------------------------------------------------------- photos

@app.post("/api/wines/{wine_id}/photos", status_code=201)
async def add_photos(wine_id: int, photos: list[UploadFile] = File(...), user: dict = Depends(current_user)):
    """Add a photo later (e.g. a forgotten back label)."""
    wine = _get_wine(user["id"], wine_id)
    if wine["photo_count"] + len(photos) > settings.max_photos_per_wine:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{settings.max_photos_per_wine} photos maximum per bottle")
    jpegs = await _read_uploads(photos)
    udir = _user_dir(user["id"])
    files = []
    for jpeg in jpegs:
        name = f"{uuid.uuid4().hex}.jpg"
        (udir / name).write_bytes(jpeg)
        files.append(name)
    with connect() as conn:
        start = conn.execute("SELECT COALESCE(MAX(position) + 1, 0) FROM photos WHERE wine_id = ?",
                             (wine_id,)).fetchone()[0]
        _attach_photos(conn, user["id"], wine_id, files, start)
    return _get_wine(user["id"], wine_id)


@app.get("/api/wines/{wine_id}/photos/{index}")
def wine_photo(wine_id: int, index: int, user: dict = Depends(current_user)):
    """Photo number `index` of a bottle (0 = front label)."""
    _get_wine(user["id"], wine_id)
    with connect() as conn:
        rows = conn.execute("SELECT file FROM photos WHERE wine_id = ? ORDER BY position", (wine_id,)).fetchall()
    if not 0 <= index < len(rows):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    return FileResponse(settings.uploads_dir / rows[index]["file"], media_type="image/jpeg")


@app.get("/api/photos/pending/{photo_id}")
def pending_photo(photo_id: str, user: dict = Depends(current_user)):
    if not _PHOTO_ID.match(photo_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid photo_id")
    path = _user_dir(user["id"]) / "pending" / f"{photo_id}.jpg"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    return FileResponse(path, media_type="image/jpeg")


# ---------------------------------------------------------------- frontend

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
