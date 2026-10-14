// Hazz Wispr dashboard. Vanilla JS; all text is rendered via textContent (no HTML injection).

const $ = (sel, root = document) => root.querySelector(sel);

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, props);
  for (const child of children) if (child != null) node.append(child);
  return node;
}

let toastTimer;
function toast(message) {
  const t = $("#toast");
  t.textContent = message;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

const fail = (e) => toast(e.message);

// --- Formatting ---------------------------------------------------------------
const nf = new Intl.NumberFormat();

function duration(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

function when(ts) {
  const d = new Date(ts * 1000);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const today = new Date().toDateString() === d.toDateString();
  return today ? `Today, ${time}` : `${d.toLocaleDateString([], { day: "numeric", month: "short" })}, ${time}`;
}

// --- Live status --------------------------------------------------------------
const STATUS = {
  loading: "Loading models…",
  ready: "Ready",
  recording: "Listening",
  processing: "Transcribing",
  permissions: "Needs permissions",
  offline: "App not running",
};
let lastSeen;

async function pollStatus() {
  let state = "offline";
  try {
    const s = await api("/api/status");
    state = s.state;
    if (s.last && s.last !== lastSeen) {
      const first = lastSeen === undefined;
      lastSeen = s.last;
      $("#last-dictation").textContent = s.last;
      if (!first && route() === "overview") loadOverview();
      if (!first && route() === "history") loadHistory();
    }
  } catch {}
  const pill = $("#status");
  pill.dataset.state = state;
  $(".status-label", pill).textContent = STATUS[state] || state;
  document.body.classList.toggle("is-recording", state === "recording");
}

// --- Overview -----------------------------------------------------------------
async function loadOverview() {
  try {
    const [stats, history] = await Promise.all([api("/api/stats"), api("/api/history")]);
    const set = (k, v) => ($(`[data-stat="${k}"]`).textContent = v);
    set("words", nf.format(stats.words));
    set("dictations", nf.format(stats.dictations));
    set("saved", duration(stats.seconds_saved));
    set("latency", stats.avg_latency == null ? "–" : `${stats.avg_latency.toFixed(1)}s`);

    const recent = $("#recent");
    recent.replaceChildren();
    const items = history.items.slice(0, 5);
    if (!items.length) recent.append(el("li", { className: "empty", textContent: "Your dictations will show up here." }));
    for (const h of items) {
      recent.append(el("li", {},
        el("p", { className: "feed-text", textContent: h.text }),
        el("p", { className: "meta", textContent: [when(h.created), h.app].filter(Boolean).join(" · ") })));
    }
    if (items.length && lastSeen === undefined) $("#last-dictation").textContent = items[0].text;

    const apps = $("#top-apps");
    apps.replaceChildren();
    const max = Math.max(1, ...stats.top_apps.map((a) => a.count));
    if (!stats.top_apps.length) apps.append(el("li", { className: "empty", textContent: "No data yet." }));
    for (const a of stats.top_apps) {
      const fill = el("div", { className: "bar-fill" });
      fill.style.width = `${(a.count / max) * 100}%`;
      apps.append(el("li", {},
        el("span", { className: "bar-name", textContent: a.app }),
        el("span", { className: "bar-count", textContent: nf.format(a.count) }),
        el("div", { className: "bar-track" }, fill)));
    }
  } catch (e) { fail(e); }
}

// --- Dictionary ---------------------------------------------------------------
function renderDictionary({ words, replacements }) {
  $("#word-count").textContent = words.length;
  $("#rep-count").textContent = replacements.length;

  const list = $("#words");
  list.replaceChildren();
  if (!words.length) list.append(el("li", { className: "empty", textContent: "No words yet." }));
  for (const w of words) {
    const remove = el("button", { className: "x", type: "button", textContent: "×", title: "Remove" });
    remove.setAttribute("aria-label", `Remove ${w.term}`);
    remove.onclick = () => api(`/api/dictionary/words/${w.id}`, { method: "DELETE" }).then(renderDictionary, fail);
    list.append(el("li", { className: "chip" }, w.term, remove));
  }

  const reps = $("#replacements");
  reps.replaceChildren();
  if (!replacements.length) reps.append(el("li", { className: "empty", textContent: "No replacements yet." }));
  for (const r of replacements) {
    const remove = el("button", { className: "x", type: "button", textContent: "×", title: "Remove" });
    remove.setAttribute("aria-label", `Remove replacement for ${r.source}`);
    remove.onclick = () => api(`/api/dictionary/replacements/${r.id}`, { method: "DELETE" }).then(renderDictionary, fail);
    reps.append(el("li", {},
      el("span", { className: "rep-source", textContent: r.source }),
      el("span", { className: "arrow", textContent: "→" }),
      el("span", { className: "rep-target", textContent: r.target }),
      remove));
  }
}

const loadDictionary = () => api("/api/dictionary").then(renderDictionary, fail);

$("#word-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  api("/api/dictionary/words", { method: "POST", body: { term: form.term.value } })
    .then((d) => { form.reset(); renderDictionary(d); toast("Word added"); }, fail);
});

$("#rep-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  api("/api/dictionary/replacements", { method: "POST", body: { source: form.source.value, target: form.target.value } })
    .then((d) => { form.reset(); form.source.focus(); renderDictionary(d); toast("Replacement added"); }, fail);
});

// --- History ------------------------------------------------------------------
async function loadHistory() {
  const q = $("#history-search").value.trim();
  try {
    const { items } = await api(`/api/history?q=${encodeURIComponent(q)}`);
    const list = $("#history");
    list.replaceChildren();
    if (!items.length) {
      list.append(el("li", { className: "empty", textContent: q ? "No matches." : "Nothing here yet. Hold Right Option and say something." }));
    }
    for (const h of items) {
      const copy = el("button", { className: "mini", type: "button", textContent: "Copy" });
      copy.onclick = () => navigator.clipboard.writeText(h.text).then(() => toast("Copied"), fail);
      const actions = el("div", { className: "entry-actions" }, copy);
      const entry = el("li", { className: "entry" });
      if (h.raw !== h.text) {
        const raw = el("p", { className: "entry-raw", textContent: `Heard: ${h.raw}`, hidden: true });
        const toggle = el("button", { className: "mini", type: "button", textContent: "Original" });
        toggle.onclick = () => (raw.hidden = !raw.hidden);
        actions.prepend(toggle);
        entry.append(raw);
      }
      const del = el("button", { className: "mini", type: "button", textContent: "Delete" });
      del.onclick = () => api(`/api/history/${h.id}`, { method: "DELETE" }).then(() => entry.remove(), fail);
      actions.append(del);
      entry.prepend(
        el("div", { className: "entry-top" },
          h.app ? el("span", { className: "app-tag", textContent: h.app }) : null,
          el("span", { className: "meta", textContent: `${when(h.created)} · ${h.latency.toFixed(1)}s` }),
          actions),
        el("p", { className: "entry-text", textContent: h.text }));
      list.append(entry);
    }
  } catch (e) { fail(e); }
}

let searchTimer;
$("#history-search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadHistory, 200);
});

$("#clear-history").addEventListener("click", () => {
  if (!confirm("Delete all saved dictations? Stats are kept.")) return;
  api("/api/history", { method: "DELETE" }).then(() => { loadHistory(); toast("History cleared"); }, fail);
});

// --- Settings -----------------------------------------------------------------
async function loadSettings() {
  try {
    const [s, { models }] = await Promise.all([api("/api/settings"), api("/api/models")]);
    for (const input of document.querySelectorAll("[data-setting]")) input.checked = !!s[input.dataset.setting];
    const login = $('[data-setting="start_at_login"]');
    login.disabled = !s.login_available;
    $("#login-desc").textContent = s.login_available
      ? "Open Hazz Wispr in the menu bar when you log in."
      : "Available when Hazz Wispr is opened as an app (not from Terminal).";

    const select = $("#model-select");
    select.replaceChildren();
    const names = models && models.length ? models : [s.ollama_model];
    if (!names.includes(s.ollama_model)) names.unshift(s.ollama_model);
    for (const name of names) select.append(el("option", { value: name, textContent: name, selected: name === s.ollama_model }));
    select.disabled = !models;
    $("#model-desc").textContent = models
      ? "Bigger models handle corrections better but are slower."
      : "Ollama isn't running. Open the Ollama app to enable cleanup.";
  } catch (e) { fail(e); }
}

for (const input of document.querySelectorAll("[data-setting]")) {
  input.addEventListener("change", () => {
    api("/api/settings", { method: "POST", body: { [input.dataset.setting]: input.checked } })
      .then(() => toast("Saved"), (e) => { input.checked = !input.checked; fail(e); });
  });
}

$("#model-select").addEventListener("change", (e) => {
  api("/api/settings", { method: "POST", body: { ollama_model: e.target.value } }).then(() => toast("Saved"), fail);
});

// --- Router -------------------------------------------------------------------
const VIEWS = { overview: loadOverview, dictionary: loadDictionary, history: loadHistory, settings: loadSettings };
const route = () => (location.hash.slice(1) in VIEWS ? location.hash.slice(1) : "overview");

function show() {
  const name = route();
  for (const v of document.querySelectorAll(".view")) v.hidden = v.id !== `view-${name}`;
  for (const a of document.querySelectorAll(".nav a")) {
    a.toggleAttribute("aria-current", a.getAttribute("href") === `#${name}`);
    if (a.hasAttribute("aria-current")) a.setAttribute("aria-current", "page");
  }
  VIEWS[name]();
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", show);
show();
pollStatus();
setInterval(pollStatus, 700);
