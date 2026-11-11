"use strict";
/* Wineremember — framework-free frontend. Hash routing (e.g. #history?region=Burgundy). */

const $view = document.getElementById("view");
const MAX_PHOTOS = 4;
const COLORS = {
  red: "#7b1e34", white: "#e8d785", "rosé": "#f0a3b4", sparkling: "#d8cf9f",
  sweet: "#d79a2b", orange: "#e08a3c", other: "#999",
};
const CATEGORIES = [
  { key: "producers", param: "producer", label: "Producers", icon: "🏰" },
  { key: "regions", param: "region", label: "Regions", icon: "🗺️" },
  { key: "vintages", param: "vintage", label: "Vintages", icon: "📅" },
  { key: "appellations", param: "appellation", label: "Appellations", icon: "📍" },
  { key: "countries", param: "country", label: "Countries", icon: "🌍" },
  { key: "colors", param: "color", label: "Colors", icon: "🍷" },
];
// Suggested reference sites (one-click add in the Sources tab)
const SUGGESTED_SOURCES = [
  { url: "https://www.wine-searcher.com", label: "Wine-Searcher" },
  { url: "https://www.jancisrobinson.com", label: "Jancis Robinson" },
  { url: "https://www.decanter.com", label: "Decanter" },
  { url: "https://www.larvf.com", label: "La Revue du Vin de France" },
  { url: "https://www.vinous.com", label: "Vinous" },
];
const FILTER_LABELS = { producer: "Producer", region: "Region", vintage: "Vintage",
  appellation: "Appellation", country: "Country", color: "Color" };

// ------------------------------------------------------------ utilities

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const token = {
  get: () => { try { return localStorage.getItem("token"); } catch { return null; } },
  set: (t) => { try { t ? localStorage.setItem("token", t) : localStorage.removeItem("token"); } catch {} },
};

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg; el.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (el.hidden = true), 3500);
}

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: form || (body && JSON.stringify(body)) });
  if (res.status === 401) { token.set(null); location.hash = "#login"; throw new Error("Session expired"); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((e) => e.msg).join(", ") : `Error ${res.status}`);
  }
  return data;
}

/** Photos are protected: load them with the token, then as a blob. */
async function loadImg(img, url) {
  try {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token.get()}` } });
    if (res.ok) img.src = URL.createObjectURL(await res.blob());
  } catch {}
}
function hydrateImages(root = $view) {
  root.querySelectorAll("img[data-src]").forEach((img) => { loadImg(img, img.dataset.src); img.removeAttribute("data-src"); });
}

const plural = (n, word) => `${n} ${word}${n > 1 ? "s" : ""}`;
const stars = (n) => (n ? `<span class="stars-static">${"★".repeat(n)}${"☆".repeat(5 - n)}</span>` : "");
const colorDot = (c) => (c ? `<span class="color-dot" style="background:${COLORS[c] || "#999"}"></span>${esc(c)}` : "");
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "");
const title = (w) => esc([w.producer && w.producer !== w.name ? w.producer : null, w.name].filter(Boolean).join(" — "));
const catLink = (param, value) => `#history?${new URLSearchParams({ [param]: value })}`;
const photoLabel = (i) => (i === 0 ? "Front" : i === 1 ? "Back" : `Photo ${i + 1}`);

function wineItem(w, extra = "") {
  return `<a class="card wine-item" href="#wine/${w.id}">
    ${w.has_photo ? `<img class="thumb" data-src="/api/wines/${w.id}/photos/0" alt="">` : `<div class="thumb"></div>`}
    <div class="body">
      <div class="title">${title(w)}</div>
      <div class="small muted">${[w.vintage, w.appellation || w.region].filter(Boolean).map(esc).join(" · ")}</div>
      <div class="small">${stars(w.rating)} ${w.tasted_on ? `<span class="muted">${fmtDate(w.tasted_on)}</span>` : ""}</div>
      ${extra}
    </div></a>`;
}

function gallery(urls) {
  if (!urls.length) return "";
  return `<div class="gallery">${urls.map((u, i) =>
    `<figure><img data-src="${u}" alt=""><figcaption>${photoLabel(i)}</figcaption></figure>`).join("")}</div>`;
}

/** Wine sheet grouped by category: each value links to every wine in that category. */
function categorySheet(w) {
  const rows = [
    ["🏰", "Producer", w.producer || w.name, "producer"],
    ["🍾", "Wine", w.name, null],
    ["📅", "Vintage", w.vintage || "Non-vintage", w.vintage ? "vintage" : null],
    ["🗺️", "Region", w.region, "region"],
    ["📍", "Appellation", w.appellation, "appellation"],
    ["🌍", "Country", w.country, "country"],
  ].filter(([, , v]) => v);
  return `<div class="card sheet">${rows.map(([icon, label, value, param]) => `
    <div class="sheet-row"><span class="muted">${icon} ${label}</span>
      ${param ? `<a href="${catLink(param, value)}">${esc(value)} ›</a>` : `<b>${esc(value)}</b>`}</div>`).join("")}
    ${w.color || (w.grapes || []).length ? `<div style="margin-top:6px">${w.color ? `<span class="chip">${colorDot(w.color)}</span>` : ""}
      ${(w.grapes || []).map((g) => `<span class="chip">${esc(g)}</span>`).join("")}</div>` : ""}
  </div>`;
}

const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? esc(u) : "#");
const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

function linkList(links, { deletable }) {
  return links.map((l) => `<div class="sheet-row">
      <a href="${safeUrl(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label || host(l.url))} ↗</a>
      ${deletable ? `<button class="link small" data-del-link="${l.id}">✕</button>` : ""}</div>`).join("");
}

function dossierHtml(d) {
  if (!d) return "";
  const block = (icon, t, body) => (body ? `<h4>${icon} ${t}</h4><p>${esc(body)}</p>` : "");
  return `<div class="card dossier">
    ${block("🍾", "The wine", d.wine_description)}
    ${block("👃", "Tasting profile", d.tasting_profile)}
    ${block("🏰", "The producer", d.producer_description)}
    ${d.producer_website ? `<p><a href="${safeUrl(d.producer_website)}" target="_blank" rel="noopener noreferrer">Producer's website ↗</a></p>` : ""}
    ${block("🗺️", "The region", d.region_description)}
    ${block("📅", "The vintage", d.vintage_description)}
    ${block("⏳", "Drinking window", d.drinking_window)}
    ${d.food_pairings?.length ? `<h4>🍽️ Food pairings</h4><div>${d.food_pairings.map((f) => `<span class="chip">${esc(f)}</span>`).join("")}</div>` : ""}
    ${d.critic_scores?.length ? `<h4>⭐ Critics</h4><ul>${d.critic_scores.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
    ${d.sources?.length ? `<h4>🔗 Sources</h4>${linkList(d.sources.map((s) => ({ url: s.url, label: s.title })), { deletable: false })}` : ""}
    <p class="small muted">Researched on ${fmtDate(d.updated_at)}</p>
  </div>`;
}

/** Empty fields on the wine record that the web research can fill in. */
function fillableFields(w, d) {
  const s = d?.suggested_fields;
  if (!s) return {};
  const out = {};
  for (const k of ["producer", "appellation", "region", "country", "classification"]) {
    if (!w[k] && s[k]) out[k] = s[k];
  }
  if (!(w.grapes || []).length && (s.grapes || []).length) out.grapes = s.grapes;
  return out;
}

function parseHash() {
  const [path, query = ""] = location.hash.slice(1).split("?");
  const [name, arg] = (path || "scan").split("/");
  return { name, arg, params: new URLSearchParams(query) };
}

// ------------------------------------------------------------ views

const views = {};

views.login = () => {
  $view.innerHTML = `
    <div class="scan-hero"><div style="font-size:64px">🍷</div><h2>Wineremember</h2>
    <p class="muted">Snap every wine you taste and find it again in seconds.</p></div>
    <form class="card" id="auth">
      <label>Username</label><input name="username" autocomplete="username" required minlength="3">
      <label>Password</label><input name="password" type="password" autocomplete="current-password" required minlength="6">
      <div class="row" style="margin-top:16px">
        <button type="submit" name="mode" value="login">Sign in</button>
        <button type="submit" name="mode" value="register" class="secondary">Create account</button>
      </div>
    </form>`;
  document.getElementById("auth").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const mode = e.submitter?.value || "login";
    try {
      const r = await api(`/api/auth/${mode}`, { method: "POST",
        body: { username: fd.get("username"), password: fd.get("password") } });
      token.set(r.token);
      location.hash = pendingShare ? "#share" : "#scan";
    } catch (err) { toast(err.message); }
  });
};

views.scan = async () => {
  let shots = [];  // photos of the current bottle: front, back...
  $view.innerHTML = `
    <div class="stats" id="stats"></div>
    <div id="capture"></div>
    <input type="file" id="camera" accept="image/*" capture="environment" hidden>
    <input type="file" id="library" accept="image/*" multiple hidden>`;
  const camera = document.getElementById("camera");
  const library = document.getElementById("library");
  const box = document.getElementById("capture");

  const render = () => {
    if (!shots.length) {
      box.innerHTML = `<div class="scan-hero">
        <button class="scan-btn" id="shoot"><span>📷</span>Photograph<br>the front label</button>
        <p class="muted small" style="margin-top:20px">Frame the label well. You can add the back label next.</p>
        <div class="row" style="justify-content:center">
          <button class="link" id="pick">Import from photo library</button>
        </div>
        <button class="link small" id="manual" style="margin-top:10px">or enter a wine by hand</button>
      </div>`;
      box.querySelector("#shoot").onclick = () => camera.click();
      box.querySelector("#pick").onclick = () => library.click();
      box.querySelector("#manual").onclick = () => showResult({ photo_ids: [], label: { is_wine_label: true, grapes: [] },
        already_tasted: { same_vintage: [], other_vintages: [] }, similar: [], same_vintage_wines: [] });
      return;
    }
    box.innerHTML = `<h2>Your bottle</h2>
      <div class="gallery">${shots.map((f, i) => `<figure>
        <img src="${URL.createObjectURL(f)}" alt=""><figcaption>${photoLabel(i)}
        <button class="link small" data-rm="${i}">✕</button></figcaption></figure>`).join("")}</div>
      ${shots.length < MAX_PHOTOS ? `<button class="secondary" id="more" style="width:100%;margin:8px 0">
        📷 ${shots.length === 1 ? "Add the back label" : "Add a photo"}</button>` : ""}
      <button id="go" style="width:100%">🔍 Analyse the bottle</button>
      <button class="link small" id="reset" style="display:block;margin:12px auto">Start over</button>`;
    box.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => { shots.splice(Number(b.dataset.rm), 1); render(); }));
    box.querySelector("#more")?.addEventListener("click", () => camera.click());
    box.querySelector("#reset").onclick = () => { shots = []; render(); };
    box.querySelector("#go").onclick = analyse;
  };

  const add = (files) => { shots = [...shots, ...files].slice(0, MAX_PHOTOS); render(); };
  camera.onchange = () => { add([...camera.files]); camera.value = ""; };
  library.onchange = () => { add([...library.files]); library.value = ""; };

  async function analyse() {
    $view.innerHTML = `<div class="spinner"></div><p class="muted" style="text-align:center">
      Reading ${shots.length > 1 ? "the front and back labels" : "the label"}…</p>`;
    const form = new FormData();
    shots.forEach((f) => form.append("photos", f));
    try { showResult(await api("/api/scan", { method: "POST", form })); }
    catch (err) { toast(err.message); views.scan(); }
  }

  render();
  try {
    const { stats } = await api("/api/me");
    document.getElementById("stats").innerHTML = `
      <div class="card"><b>${stats.total}</b><span class="small muted">wines tasted</span></div>
      <div class="card"><b>${stats.producers}</b><span class="small muted">producers</span></div>
      <div class="card"><b>${stats.regions}</b><span class="small muted">regions</span></div>`;
  } catch {}
};

function wineForm(w, { submitLabel }) {
  const v = (k) => esc(w[k] ?? "");
  return `
  <form class="card" id="wine-form">
    <label>Producer / Château / Domaine</label><input name="producer" value="${v("producer")}">
    <label>Wine name *</label><input name="name" value="${v("name")}" required>
    <div class="grid2">
      <div><label>Vintage</label><input name="vintage" type="number" min="1800" max="2100" value="${v("vintage")}"></div>
      <div><label>Region</label><input name="region" value="${v("region")}"></div>
      <div><label>Appellation</label><input name="appellation" value="${v("appellation")}"></div>
      <div><label>Country</label><input name="country" value="${v("country")}"></div>
      <div><label>Color</label><select name="color"><option value="">—</option>
        ${Object.keys(COLORS).map((c) => `<option ${w.color === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
      <div><label>Classification</label><input name="classification" value="${v("classification")}"></div>
    </div>
    <label>Grape varieties (comma-separated)</label><input name="grapes" value="${esc((w.grapes || []).join(", "))}">
    <h3>My tasting</h3>
    <div class="stars" id="stars">${[1, 2, 3, 4, 5].map((i) =>
      `<button type="button" data-v="${i}" class="${i <= (w.rating || 0) ? "on" : ""}" aria-label="${plural(i, "star")}">★</button>`).join("")}</div>
    <input type="hidden" name="rating" value="${v("rating")}">
    <label>What I thought</label><textarea name="notes" placeholder="Nose, palate, food pairing…">${v("notes")}</textarea>
    <div class="grid2">
      <div><label>Date</label><input name="tasted_on" type="date" value="${w.tasted_on || new Date().toISOString().slice(0, 10)}"></div>
      <div><label>Occasion / place</label><input name="occasion" value="${v("occasion")}" placeholder="Trade fair, trip, dinner…"></div>
    </div>
    <button type="submit" style="width:100%;margin-top:16px">${submitLabel}</button>
  </form>`;
}

function readForm(form) {
  const fd = new FormData(form);
  const str = (k) => (fd.get(k) || "").toString().trim() || null;
  return {
    name: str("name"), producer: str("producer"),
    vintage: str("vintage") ? Number(fd.get("vintage")) : null,
    color: str("color"), appellation: str("appellation"), region: str("region"),
    country: str("country"), classification: str("classification"),
    grapes: (fd.get("grapes") || "").split(",").map((g) => g.trim()).filter(Boolean),
    rating: str("rating") ? Number(fd.get("rating")) : null,
    notes: str("notes"), tasted_on: str("tasted_on"), occasion: str("occasion"),
  };
}

function bindStars(form) {
  const hidden = form.querySelector("[name=rating]");
  form.querySelectorAll("#stars button").forEach((b) => (b.onclick = () => {
    const val = Number(b.dataset.v) === Number(hidden.value) ? "" : b.dataset.v;  // click again = clear
    hidden.value = val;
    form.querySelectorAll("#stars button").forEach((x) => x.classList.toggle("on", Number(x.dataset.v) <= Number(val || 0)));
  }));
}

function matchesHtml(result, label) {
  const { same_vintage, other_vintages } = result.already_tasted;
  let html = "";
  if (same_vintage.length) {
    html += `<div class="banner ok"><strong>✅ You have already tasted this wine!</strong>
      ${plural(same_vintage.length, "tasting")} of this vintage.</div>`
      + same_vintage.map((w) => wineItem(w, w.notes ? `<div class="small">“${esc(w.notes.slice(0, 140))}”</div>` : "")).join("");
  }
  if (other_vintages.length) {
    html += `<div class="banner info"><strong>🍇 Already tasted in another vintage</strong></div>`
      + other_vintages.map((w) => wineItem(w)).join("");
  }
  if (!same_vintage.length && !other_vintages.length && label?.name) {
    html += `<div class="banner info"><strong>✨ New wine</strong>It is not in your history yet.</div>`;
  }
  return html;
}

function relatedHtml(result, label) {
  let html = "";
  if (result.similar?.length) {
    html += `<h3>Already tasted, similar style</h3>` + result.similar.map((w) =>
      wineItem(w, `<div>${w.reasons.map((r) => `<span class="chip">${esc(r)}</span>`).join("")}</div>`)).join("");
  }
  if (label?.vintage && result.same_vintage_wines?.length) {
    html += `<h3>Other ${esc(label.vintage)} wines you have tasted</h3>`
      + result.same_vintage_wines.map((w) => wineItem(w)).join("")
      + `<a class="small" href="${catLink("vintage", label.vintage)}">See all ${esc(label.vintage)} wines ›</a>`;
  }
  return html;
}

function suggestionsBlock(getRef) {
  const wrap = document.createElement("div");
  wrap.innerHTML = `<h3>Discover similar wines</h3>
    <button class="secondary" style="width:100%">✨ AI sommelier suggestions</button><div class="sugg"></div>`;
  const btn = wrap.querySelector("button");
  btn.onclick = async () => {
    const out = wrap.querySelector(".sugg");
    btn.disabled = true; out.innerHTML = `<div class="spinner"></div>`;
    try {
      const { suggestions } = await api("/api/suggestions", { method: "POST", body: getRef() });
      out.innerHTML = suggestions.length ? suggestions.map((s) => `<div class="card">
          <div class="title"><b>${title(s)}</b></div>
          <div class="small muted">${colorDot(s.color)} ${[s.appellation, s.region].filter(Boolean).map(esc).join(" · ")}
            ${s.price_hint ? ` · ${esc(s.price_hint)}` : ""}</div>
          <div>${(s.grapes || []).map((g) => `<span class="chip">${esc(g)}</span>`).join("")}</div>
          <p class="small" style="margin:6px 0 0">${esc(s.why)}</p></div>`).join("")
        : `<p class="muted">No suggestions for now.</p>`;
    } catch (err) { out.innerHTML = ""; toast(err.message); }
    btn.disabled = false;
  };
  return wrap;
}

function showResult(result) {
  if (pendingShare) { result.shared_url = pendingShare; pendingShare = null; }
  const l = result.label;
  if (!l.is_wine_label) {
    toast("This doesn't look like a wine label… try again closer.");
    return views.scan();
  }
  const scanned = result.photo_ids.length > 0;
  $view.innerHTML = `
    ${gallery(result.photo_ids.map((id) => `/api/photos/pending/${id}`))}
    ${scanned && l.name ? categorySheet(l) : ""}
    ${l.confidence === "low" ? `<div class="banner info small">Uncertain reading: please check the fields below.</div>` : ""}
    <div id="matches">${matchesHtml(result, l)}</div>
    <h2>${scanned ? "Check and rate" : "New wine"}</h2>
    ${wineForm(l, { submitLabel: "Add to my history" })}
    <div id="related">${relatedHtml(result, l)}</div>`;
  // Optional link + automatic web research when saving
  document.querySelector("#wine-form button[type=submit]").insertAdjacentHTML("beforebegin", `
    <label>Link about this wine (optional)</label>
    <input name="link" type="url" placeholder="https://… technical sheet, estate page" value="${esc(result.shared_url || "")}">
    <label class="check"><input type="checkbox" name="research" checked> Look up information on the internet</label>`);
  hydrateImages();
  const form = document.getElementById("wine-form");
  bindStars(form);

  // A field corrected by hand -> search the history again.
  let t;
  form.addEventListener("input", (e) => {
    if (!["name", "producer", "vintage", "appellation", "color", "grapes", "region", "country"].includes(e.target.name)) return;
    clearTimeout(t);
    t = setTimeout(async () => {
      const ref = readForm(form);
      if (!ref.name) return;
      try {
        const r = await api("/api/lookup", { method: "POST", body: ref });
        document.getElementById("matches").innerHTML = matchesHtml(r, ref);
        document.getElementById("related").innerHTML = relatedHtml(r, ref);
        hydrateImages();
      } catch {}
    }, 500);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const link = form.elements.link.value.trim();
    if (link && !/^https?:\/\//i.test(link)) { toast("The link must start with http:// or https://"); return; }
    try {
      const w = await api("/api/wines", { method: "POST", body: { ...readForm(form), photo_ids: result.photo_ids } });
      if (link) await api(`/api/wines/${w.id}/links`, { method: "POST", body: { url: link } }).catch((e) => toast(e.message));
      toast("Wine added to your history 🍷");
      location.hash = `#wine/${w.id}${form.elements.research.checked ? "?research=1" : ""}`;
    } catch (err) { toast(err.message); }
  });
  $view.appendChild(suggestionsBlock(() => readForm(form)));
}

views.categories = async (_, params) => {
  const active = CATEGORIES.find((c) => c.key === params.get("by")) || CATEGORIES[0];
  $view.innerHTML = `
    <h2>My wines by category</h2>
    <div class="segmented">${CATEGORIES.map((c) =>
      `<a href="#categories?by=${c.key}" class="${c === active ? "on" : ""}">${c.icon} ${c.label}</a>`).join("")}</div>
    <div id="groups"><div class="spinner"></div></div>`;
  try {
    const cats = await api("/api/categories");
    const groups = cats[active.key];
    document.getElementById("groups").innerHTML = groups.length
      ? `<div class="card">${groups.map((g) => `
          <a class="group-row" href="${catLink(active.param, g.value)}">
            <span>${active.param === "color" ? colorDot(g.value) : esc(g.value)}</span>
            <span class="count">${plural(g.count, "wine")} ›</span></a>`).join("")}</div>`
      : `<p class="muted" style="text-align:center">Nothing to show yet: scan your first bottle!</p>`;
  } catch (err) { toast(err.message); }
};

views.history = async (_, params) => {
  const filters = Object.keys(FILTER_LABELS).filter((k) => params.get(k));
  $view.innerHTML = `
    <h2>My history</h2>
    ${filters.length ? `<div style="margin-bottom:8px">${filters.map((k) =>
      `<a class="chip filter" href="#history?${(() => { const p = new URLSearchParams(params); p.delete(k); return p; })()}">
        ${FILTER_LABELS[k]}: ${esc(params.get(k))} ✕</a>`).join("")}</div>` : ""}
    <input id="q" type="search" placeholder="Search: producer, wine, region, grape, vintage…" value="${esc(params.get("q") || "")}">
    <div class="row" style="margin:8px 0 12px">
      <select id="sort"><option value="recent">Most recent</option><option value="rating">Best rated</option>
        <option value="vintage">Vintage</option><option value="name">Producer</option></select>
      <a class="btn secondary" href="#categories" style="text-align:center;text-decoration:none">Categories</a>
    </div>
    <div id="list"><div class="spinner"></div></div>`;
  const load = async () => {
    const p = new URLSearchParams();
    filters.forEach((k) => p.set(k, params.get(k)));
    const q = document.getElementById("q").value.trim();
    if (q) p.set("q", q);
    p.set("sort", document.getElementById("sort").value);
    try {
      const wines = await api(`/api/wines?${p}`);
      document.getElementById("list").innerHTML = (wines.length
        ? `<p class="small muted">${plural(wines.length, "wine")}</p>` + wines.map((w) => wineItem(w)).join("")
        : `<p class="muted" style="text-align:center">${q || filters.length ? "No results." : "No wines yet. Scan your first bottle!"}</p>`);
      hydrateImages();
    } catch (err) { toast(err.message); }
  };
  let t;
  document.getElementById("q").oninput = () => { clearTimeout(t); t = setTimeout(load, 250); };
  document.getElementById("sort").onchange = load;
  load();
};

views.wine = async (id, params = new URLSearchParams()) => {
  $view.innerHTML = `<div class="spinner"></div>`;
  let w;
  try { w = await api(`/api/wines/${id}`); } catch (err) { toast(err.message); location.hash = "#history"; return; }
  const others = [...w.already_tasted.same_vintage, ...w.already_tasted.other_vintages];
  const photos = Array.from({ length: w.photo_count }, (_, i) => `/api/wines/${w.id}/photos/${i}?v=${w.photo_count}`);
  $view.innerHTML = `
    <button class="link" onclick="history.back()">‹ Back</button>
    ${gallery(photos)}
    ${w.photo_count < MAX_PHOTOS ? `<button class="link small" id="addphoto">📷 ${w.photo_count === 1 ? "Add the back label" : "Add a photo"}</button>
      <input type="file" id="addfile" accept="image/*" capture="environment" hidden>` : ""}
    <h2>${title(w)} ${w.vintage ? esc(w.vintage) : ""}</h2>
    ${categorySheet(w)}

    <h3>🌐 On the internet</h3>
    <div id="dossier">${dossierHtml(w.dossier)}</div>
    <div id="fill"></div>
    <button class="secondary" id="research" style="width:100%">
      ${w.dossier ? "🔄 Update the information" : "🌐 Look up the wine, producer, region and vintage"}</button>

    <h3>🔗 My links for this wine</h3>
    <div class="card" id="links">${w.links.length ? linkList(w.links, { deletable: true })
      : `<p class="small muted" style="margin:0">Add the technical sheet, the estate page, an article… They are read first during the research.</p>`}</div>
    <form class="row" id="link-form" style="margin-bottom:8px">
      <input name="url" type="url" required placeholder="https://…" style="flex:3">
      <button type="submit" style="flex:1">Add</button>
    </form>

    ${others.length ? `<h3>My other tastings of this wine</h3>${others.map((o) => wineItem(o)).join("")}` : ""}
    ${wineForm(w, { submitLabel: "Save changes" })}
    <button class="danger" id="del" style="width:100%">Delete this wine</button>
    <div id="related">${relatedHtml(w, w)}</div>`;
  hydrateImages();

  // --- Web research
  const researchBtn = document.getElementById("research");
  const showFill = (dossier) => {
    const fill = fillableFields(w, dossier);
    const box = document.getElementById("fill");
    const keys = Object.keys(fill);
    if (!keys.length) { box.innerHTML = ""; return; }
    box.innerHTML = `<button id="apply" style="width:100%;margin-bottom:8px">✍️ Complete the record (${plural(keys.length, "detail")} found)</button>`;
    document.getElementById("apply").onclick = async () => {
      try { await api(`/api/wines/${id}`, { method: "PATCH", body: fill }); toast("Record completed"); views.wine(id); }
      catch (err) { toast(err.message); }
    };
  };
  const runResearch = async () => {
    researchBtn.disabled = true;
    document.getElementById("dossier").innerHTML = `<div class="spinner"></div>
      <p class="muted small" style="text-align:center">Reading your links and searching the internet… (about 1 minute)</p>`;
    try {
      const d = await api(`/api/wines/${id}/research`, { method: "POST" });
      document.getElementById("dossier").innerHTML = dossierHtml(d);
      researchBtn.textContent = "🔄 Update the information";
      showFill(d);
    } catch (err) { document.getElementById("dossier").innerHTML = dossierHtml(w.dossier); toast(err.message); }
    researchBtn.disabled = false;
  };
  researchBtn.onclick = runResearch;
  showFill(w.dossier);
  if (params.get("research") === "1") {
    history.replaceState(null, "", `#wine/${id}`);  // don't run it again when coming back to the page
    if (!w.dossier) runResearch();
  }

  // --- Wine links
  document.getElementById("link-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api(`/api/wines/${id}/links`, { method: "POST", body: { url: e.target.url.value.trim() } });
      toast("Link added: it will be used in the next research"); views.wine(id);
    } catch (err) { toast(err.message); }
  });
  document.querySelectorAll("[data-del-link]").forEach((b) => (b.onclick = async () => {
    try { await api(`/api/wines/${id}/links/${b.dataset.delLink}`, { method: "DELETE" }); views.wine(id); }
    catch (err) { toast(err.message); }
  }));

  const addfile = document.getElementById("addfile");
  if (addfile) {
    document.getElementById("addphoto").onclick = () => addfile.click();
    addfile.onchange = async () => {
      if (!addfile.files[0]) return;
      const form = new FormData(); form.append("photos", addfile.files[0]);
      try { await api(`/api/wines/${id}/photos`, { method: "POST", form }); toast("Photo added"); views.wine(id); }
      catch (err) { toast(err.message); }
    };
  }
  const form = document.getElementById("wine-form");
  bindStars(form);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api(`/api/wines/${id}`, { method: "PATCH", body: readForm(form) }); toast("Changes saved"); views.wine(id); }
    catch (err) { toast(err.message); }
  });
  document.getElementById("del").onclick = async () => {
    if (!confirm("Permanently delete this wine from your history?")) return;
    try { await api(`/api/wines/${id}`, { method: "DELETE" }); toast("Wine deleted"); location.hash = "#history"; }
    catch (err) { toast(err.message); }
  };
  $view.appendChild(suggestionsBlock(() => readForm(form)));
};

views.sources = async () => {
  $view.innerHTML = `
    <h2>My sources</h2>
    <p class="muted small">The sites you add here (guides, critics, producer sites, vintage charts…) are
      consulted first on every internet research, in addition to each wine's own links.</p>
    <form class="card" id="src-form">
      <label>Website address</label><input name="url" type="url" required placeholder="https://…">
      <label>Name (optional)</label><input name="label" placeholder="e.g. Bettane+Desseauve guide">
      <button type="submit" style="width:100%;margin-top:12px">Add source</button>
    </form>
    <div class="card" id="src-list"><div class="spinner"></div></div>
    <h3>Suggestions</h3><div id="src-sugg"></div>`;
  const load = async () => {
    try {
      const sources = await api("/api/sources");
      document.getElementById("src-list").innerHTML = sources.length
        ? sources.map((s) => `<div class="sheet-row">
            <a href="${safeUrl(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.label || host(s.url))} ↗</a>
            <button class="link small" data-del="${s.id}">✕</button></div>`).join("")
        : `<p class="small muted" style="margin:0">No sources yet.</p>`;
      document.querySelectorAll("#src-list [data-del]").forEach((b) => (b.onclick = async () => {
        await api(`/api/sources/${b.dataset.del}`, { method: "DELETE" }).catch((e) => toast(e.message)); load();
      }));
      const known = new Set(sources.map((s) => s.url.replace(/\/$/, "")));
      document.getElementById("src-sugg").innerHTML = SUGGESTED_SOURCES.filter((s) => !known.has(s.url))
        .map((s, i) => `<button class="chip filter" data-sugg="${i}">+ ${esc(s.label)}</button>`).join("");
      document.querySelectorAll("[data-sugg]").forEach((b) => (b.onclick = async () => {
        const s = SUGGESTED_SOURCES[Number(b.dataset.sugg)];
        await api("/api/sources", { method: "POST", body: s }).catch((e) => toast(e.message)); load();
      }));
    } catch (err) { toast(err.message); }
  };
  document.getElementById("src-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api("/api/sources", { method: "POST", body: { url: fd.get("url").trim(), label: fd.get("label").trim() || null } });
      e.target.reset(); toast("Source added"); load();
    } catch (err) { toast(err.message); }
  });
  load();
};

/** Link received from another app's "Share" button (Android: manifest share_target). */
views.share = async () => {
  const url = pendingShare;
  if (!url) { location.hash = "#scan"; return; }
  $view.innerHTML = `
    <h2>Link received</h2>
    <div class="card"><a href="${safeUrl(url)}" target="_blank" rel="noopener noreferrer">${esc(host(url))} ↗</a>
      <div class="small muted" style="word-break:break-all">${esc(url)}</div></div>
    <button id="as-source" class="secondary" style="width:100%;margin-bottom:8px">📚 Add to my sources</button>
    <button id="as-new" style="width:100%">📷 New wine with this link</button>
    <h3>…or attach it to a wine in my history</h3>
    <input id="q" type="search" placeholder="Search for a wine…">
    <div id="list" style="margin-top:8px"></div>`;
  document.getElementById("as-source").onclick = async () => {
    try { await api("/api/sources", { method: "POST", body: { url } }); pendingShare = null; toast("Source added"); location.hash = "#sources"; }
    catch (err) { toast(err.message); }
  };
  document.getElementById("as-new").onclick = () => { location.hash = "#scan"; };  // the link will be prefilled
  const load = async () => {
    const q = document.getElementById("q").value.trim();
    const wines = await api(`/api/wines?${new URLSearchParams(q ? { q } : {})}`).catch(() => []);
    document.getElementById("list").innerHTML = wines.slice(0, 20).map((w) =>
      `<button class="card wine-pick" data-id="${w.id}">${title(w)} ${w.vintage ? esc(w.vintage) : ""}</button>`).join("");
    document.querySelectorAll(".wine-pick").forEach((b) => (b.onclick = async () => {
      try {
        await api(`/api/wines/${b.dataset.id}/links`, { method: "POST", body: { url } });
        pendingShare = null; toast("Link attached to the wine");
        location.hash = `#wine/${b.dataset.id}?research=1`;
      } catch (err) { toast(err.message); }
    }));
  };
  let t;
  document.getElementById("q").oninput = () => { clearTimeout(t); t = setTimeout(load, 250); };
  load();
};

// ------------------------------------------------------------ incoming share

let pendingShare = null;
(() => {
  const p = new URLSearchParams(location.search);
  const candidate = p.get("url") || (p.get("text") || "").match(/https?:\/\/\S+/)?.[0];
  if (candidate && /^https?:\/\//i.test(candidate)) {
    pendingShare = candidate;
    history.replaceState(null, "", `/#share`);
  }
})();

// ------------------------------------------------------------ router

function route() {
  const { name, arg, params } = parseHash();
  const logged = !!token.get();
  if (!logged && name !== "login") { location.hash = "#login"; return; }  // a shared link stays pending
  if (logged && name === "login") { location.hash = "#scan"; return; }
  document.getElementById("topbar").hidden = !logged;
  document.getElementById("tabbar").hidden = !logged;
  const tab = name === "wine" ? "history" : name;
  document.querySelectorAll(".tabbar a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  window.scrollTo(0, 0);
  (views[name] || views.scan)(arg, params);
}

document.getElementById("logout").onclick = async () => {
  try { await api("/api/auth/logout", { method: "POST" }); } catch {}
  token.set(null); location.hash = "#login";
};
window.addEventListener("hashchange", route);
route();
