"""Recognise a wine already tasted and find similar wines in the history.

Everything is computed locally (no AI call): fast, free and deterministic.
AI is only used to read the label and to suggest wines outside the history
(see vision.py).
"""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Iterable

# Words too common to help tell two wines apart (French, English, Spanish, Italian, German).
_STOPWORDS = {
    "chateau", "domaine", "dom", "clos", "maison", "cave", "caves", "cellier",
    "vignobles", "vignoble", "famille", "les", "le", "la", "de", "du", "des",
    "d", "l", "et", "the", "wine", "wines", "estate", "bodega", "bodegas",
    "tenuta", "weingut", "cuvee", "vin", "grand", "vins",
}


def normalize(text: str | None) -> str:
    """Lowercase, no accents or punctuation: 'Château Léoville-Poyferré' -> 'chateau leoville poyferre'."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def tokens(text: str | None) -> set[str]:
    return {t for t in normalize(text).split() if t not in _STOPWORDS and not t.isdigit()}


def match_key(name: str | None, producer: str | None) -> str:
    """Stable producer+name key, independent of word order and stopwords."""
    return " ".join(sorted(tokens(name) | tokens(producer)))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def identity_score(label: dict[str, Any], wine: dict[str, Any]) -> float:
    """Likelihood (0..1) that `label` and `wine` are the same cuvée, ignoring the vintage."""
    ka = match_key(label.get("name"), label.get("producer"))
    kb = match_key(wine.get("name"), wine.get("producer"))
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    ta, tb = set(ka.split()), set(kb.split())
    token_sim = _jaccard(ta, tb)
    # Containment: 'lynch bages' vs 'lynch bages pauillac' -> strong resemblance
    containment = len(ta & tb) / min(len(ta), len(tb))
    fuzzy = SequenceMatcher(None, ka, kb).ratio()
    score = max(token_sim, 0.9 * containment, fuzzy)
    # Same appellation: small bonus; different appellations: penalty
    app_a, app_b = normalize(label.get("appellation")), normalize(wine.get("appellation"))
    if app_a and app_b:
        score = min(1.0, score + 0.05) if app_a == app_b else score * 0.85
    return round(score, 3)


IDENTITY_THRESHOLD = 0.82


def find_already_tasted(label: dict[str, Any], history: Iterable[dict[str, Any]]) -> dict[str, list]:
    """Split the history into 'same wine, same vintage' and 'same wine, other vintage'."""
    same_vintage, other_vintages = [], []
    for wine in history:
        score = identity_score(label, wine)
        if score < IDENTITY_THRESHOLD:
            continue
        entry = {**wine, "match_score": score}
        if label.get("vintage") and wine.get("vintage") == label.get("vintage"):
            same_vintage.append(entry)
        else:
            other_vintages.append(entry)
    key = lambda w: (-w["match_score"], w.get("tasted_on") or "")
    return {"same_vintage": sorted(same_vintage, key=key), "other_vintages": sorted(other_vintages, key=key)}


# Criteria weights for style similarity.
_WEIGHTS = {"color": 0.30, "grapes": 0.25, "appellation": 0.20, "region": 0.15, "country": 0.10}


def similarity(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, list[str]]:
    """Style resemblance (0..1) and human-readable reasons."""
    score, reasons = 0.0, []

    ca, cb = a.get("color"), b.get("color")
    if ca and cb:
        if ca == cb:
            score += _WEIGHTS["color"]
        else:
            return 0.0, []  # a red does not resemble a white

    ga = {normalize(g) for g in a.get("grapes") or []}
    gb = {normalize(g) for g in b.get("grapes") or []}
    if ga and gb:
        j = _jaccard(ga, gb)
        if j:
            score += _WEIGHTS["grapes"] * j
            common = sorted(g for g in (b.get("grapes") or []) if normalize(g) in ga)
            reasons.append("grape" + ("s" if len(common) > 1 else "") + ": " + ", ".join(common))

    for field, label in (("appellation", "same appellation"), ("region", "same region"), ("country", "same country")):
        va, vb = normalize(a.get(field)), normalize(b.get(field))
        if va and va == vb:
            score += _WEIGHTS[field]
            reasons.append(f"{label} ({b.get(field)})")

    return round(score, 3), reasons


def find_similar(
    label: dict[str, Any],
    history: Iterable[dict[str, Any]],
    exclude_ids: set[int] = frozenset(),
    limit: int = 6,
    min_score: float = 0.35,
) -> list[dict[str, Any]]:
    """History wines with a similar style; on equal scores, the best-rated come first."""
    results = []
    for wine in history:
        if wine.get("id") in exclude_ids:
            continue
        score, reasons = similarity(label, wine)
        if score < min_score:
            continue
        # Wines the user liked rank slightly higher.
        rating_boost = ((wine.get("rating") or 3) - 3) * 0.03
        results.append({**wine, "similarity": round(score + rating_boost, 3), "reasons": reasons})
    results.sort(key=lambda w: -w["similarity"])
    return results[:limit]
