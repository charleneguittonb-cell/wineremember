from app.matching import find_already_tasted, find_similar, identity_score, match_key, normalize


def test_normalize_strips_accents_and_punctuation():
    assert normalize("Château Léoville-Poyferré") == "chateau leoville poyferre"


def test_match_key_ignores_stopwords_and_order():
    assert match_key("Lynch-Bages", "Château Lynch Bages") == match_key("Château Lynch-Bages", None)


def test_identity_close_names():
    a = {"name": "Château Lynch-Bages", "producer": None, "appellation": "Pauillac"}
    b = {"name": "Lynch Bages", "producer": "Château Lynch-Bages", "appellation": "Pauillac"}
    assert identity_score(a, b) >= 0.95


def test_identity_different_wines():
    a = {"name": "Château Margaux", "producer": None}
    b = {"name": "Château Palmer", "producer": None}
    assert identity_score(a, b) < 0.82


HISTORY = [
    {"id": 1, "name": "Château Lynch-Bages", "vintage": 2016, "color": "red", "appellation": "Pauillac",
     "region": "Bordeaux", "country": "France", "grapes": ["Cabernet Sauvignon", "Merlot"], "rating": 5},
    {"id": 2, "name": "Château Lynch-Bages", "vintage": 2010, "color": "red", "appellation": "Pauillac",
     "region": "Bordeaux", "country": "France", "grapes": ["Cabernet Sauvignon", "Merlot"], "rating": 4},
    {"id": 3, "name": "Château Pontet-Canet", "vintage": 2015, "color": "red", "appellation": "Pauillac",
     "region": "Bordeaux", "country": "France", "grapes": ["Cabernet Sauvignon", "Merlot"], "rating": 4},
    {"id": 4, "name": "Chablis Premier Cru", "producer": "William Fèvre", "vintage": 2020, "color": "white",
     "region": "Burgundy", "country": "France", "grapes": ["Chardonnay"], "rating": 3},
]


def test_already_tasted_splits_vintages():
    label = {"name": "Chateau Lynch Bages", "vintage": 2016, "appellation": "Pauillac"}
    res = find_already_tasted(label, HISTORY)
    assert [w["id"] for w in res["same_vintage"]] == [1]
    assert [w["id"] for w in res["other_vintages"]] == [2]


def test_similar_excludes_other_colors_and_ranks_style():
    label = {"name": "Château Pichon Baron", "color": "red", "appellation": "Pauillac",
             "region": "Bordeaux", "country": "France", "grapes": ["Cabernet Sauvignon", "Merlot"]}
    sims = find_similar(label, HISTORY)
    ids = [w["id"] for w in sims]
    assert 4 not in ids  # the white Chablis is not similar
    assert ids[0] == 1   # same profile + best rating
    assert any("same appellation" in r for r in sims[0]["reasons"])
