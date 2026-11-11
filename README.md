# 🍷 Wineremember

A mobile web app (installable on the home screen) to remember every wine you taste: at trade
fairs, on business trips, at professional tastings or with friends. No more bottle photos lost
in your phone's camera roll.

1. **Photograph the front label, then the back label** (up to 4 photos). Claude (vision) combines
   both labels to extract the **producer, wine, vintage and region**, plus appellation, country,
   color and grape varieties.
2. **A wine record grouped by category**: each bottle is filed by producer, wine, vintage and
   region. Every value is clickable to see all the wines in that category.
3. **Rate it** (1 to 5 stars), write what you thought, the date and the occasion or place.
4. **Categories tab**: your wines grouped by producer, region, vintage, appellation, country or
   color, with counts. For example, "Burgundy (12)" shows all your Burgundies.
5. **History**: free-text search and combinable filters (`region = Burgundy` + `color = white`).
6. **In front of a new bottle**, one photo is enough to know:
   - ✅ whether you have **already tasted it** (same vintage) and what you thought;
   - 🍇 whether you have tasted it **in another vintage**;
   - which wines you have tasted **with a similar style** (color, grapes, appellation, region);
   - 📅 the **other wines you have tasted from the same vintage**;
   - ✨ **AI suggestions of similar wines** you have not tasted yet.
7. **Web research (🌐)**: for each wine, Claude first reads **your links** (technical sheet, estate
   page, article…), then **your favourite sources** (Sources tab), then searches the web. It builds
   a dossier: description of the wine, the **producer**, the **region**, the **vintage** in that
   region, tasting profile, drinking window, food pairings, critic scores and **clickable sources**.
   A "Complete the record" button fills in empty fields (grapes, appellation…).
8. **Send a link to the app**: on Android, once the app is installed, the "Share" button of the
   browser or a messaging app offers Wineremember. The link can then be added to your sources,
   attached to a wine or used for a new wine.

## Architecture

```
wineremember/
├── app/                  Python backend (FastAPI)
│   ├── main.py           API routes + serves the frontend
│   ├── vision.py         Claude calls: label reading + suggestions (structured outputs)
│   ├── web_research.py   Web research (links, sources, web) → structured dossier
│   ├── matching.py       "Already tasted?" and similar wines (local, no AI)
│   ├── auth.py           Accounts (PBKDF2) and session tokens
│   ├── db.py             SQLite (schema, connection)
│   ├── schemas.py        Pydantic models (label, wine, suggestions, dossier)
│   └── config.py         Environment variables
├── frontend/             Framework-free HTML/CSS/JS PWA
└── tests/                pytest tests (Claude is simulated, no network calls)
```

**Why this split:** AI is used only for what only AI can do (reading a crooked label photo,
researching and recommending wines). "Already tasted" recognition runs locally with normalised
matching (accents, "Château", "Domaine"… ignored, fuzzy matching): instant, free and predictable.

## Installation

Requirements: **Python 3.10+** and an Anthropic API key.

```bash
cd wineremember
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # then set ANTHROPIC_API_KEY (macOS/Linux: cp)
```

Start the server (reachable from your phone on the same Wi-Fi):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` on the computer, or `http://<PC-IP-address>:8000` on the phone.

> **Phone camera:** browsers only allow direct camera access over HTTPS. Over local HTTP, the
> button still opens the "Take photo / Photo library" picker. For a real deployment, put the app
> behind an HTTPS reverse proxy (Caddy, Nginx) or a host (Render, Railway, Fly.io…).

**Try it without an API key:** set `VISION_MOCK=1` in `.env`; every scan returns a sample label
(Château Lynch-Bages 2016).

## Tests

```bash
pytest -q
```

## API

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/auth/register` · `/api/auth/login` | Create an account / sign in → token |
| POST | `/api/auth/logout` | Revoke the token |
| GET | `/api/me` | Profile + statistics |
| POST | `/api/scan` | 1 to 4 photos (multipart `photos`, front label first) → label + already tasted + similar + same vintage |
| POST | `/api/lookup` | Same lookup from typed/corrected fields |
| POST | `/api/suggestions` | Similar wines outside the history (AI) |
| GET | `/api/categories` | Wines grouped by producer, region, vintage, appellation, country, color |
| GET | `/api/wines?q=&producer=&region=&vintage=&appellation=&country=&color=&min_rating=&sort=` | History (search, filters, sorting) |
| POST | `/api/wines` | Add a tasting (with the scan's `photo_ids`) |
| GET / PATCH / DELETE | `/api/wines/{id}` | Details (+ other vintages, similar wines, links, dossier) / edit / delete |
| GET / POST / DELETE | `/api/sources` · `/api/sources/{id}` | The user's reference sites |
| POST / DELETE | `/api/wines/{id}/links` · `/api/wines/{id}/links/{link_id}` | Links attached to a wine |
| POST | `/api/wines/{id}/research` | Web research → dossier (wine, producer, region, vintage, sources) |
| GET | `/api/wines/{id}/photos/{n}` | Photo number n (0 = front, 1 = back…) |
| POST | `/api/wines/{id}/photos` | Add a photo later (e.g. a forgotten back label) |

Interactive documentation: `http://localhost:8000/docs`.

## AI model

- Default model: `claude-opus-5-5` (change it with `CLAUDE_MODEL`).
- Structured outputs (Pydantic schema `LabelInfo`): the response is always valid JSON.
- Photos are rotated (EXIF) and downsized to 1568 px before sending, to limit cost and latency.
- Web research uses Anthropic's server tools `web_fetch` and `web_search` (`_20260209` versions,
  with dynamic filtering): nothing to host. Check that web search is allowed in your
  organisation's settings on the Anthropic Console. The result is saved through a tool with a
  strict schema, so it is always structured. Expect about one minute per research; web searches
  and fetched pages are billed on top of tokens.
- Web page content is treated as information, never as instructions.
- **Server-side fallback** (`fallbacks: "default"`) is enabled: if the main model declines a
  request, the API automatically re-runs it on a fallback model.

## Roadmap

- Automatic cleanup of unsaved "pending" photos (`data/uploads/<id>/pending`).
- Native HEIC support (`pillow-heif`) for iPhone photos sent as-is.
- Cellar (bottles in stock) alongside the history, CSV export, sharing with colleagues.
- An "event" field (e.g. Vinexpo 2026, ProWein) to find everything tasted at a trade fair.
- Offline mode: photos queued at a fair with no network, analysed later.
- Image-similarity search (embeddings) to recognise a label even when it is illegible.
