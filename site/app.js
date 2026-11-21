// DMV Mission Jobs: reads data/jobs.json, renders and filters client-side. No build step.
// Every filter lives in the URL, e.g. ?umbrella=gtm,customer&public_sector=1&loc=dmv&view=list

const LEVEL_ORDER = ["intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager", "director", "vp"];
const LEVEL_LABELS = {
  intern: "Intern", junior: "Junior", mid: "Mid", senior: "Senior", staff: "Staff",
  principal: "Principal", lead: "Lead", manager: "Manager", director: "Director", vp: "VP",
};
// Fallback labels; meta.json's `taxonomy` (written by the scraper from config) wins.
const UMBRELLA_LABELS = {
  product: "Product",
  program: "Program Management",
  architecture: "Solutions / Architecture",
  gtm: "GTM / Sales / BD",
  growth: "Growth / Strategy",
  customer: "Customer Success",
  design: "Design",
  engineering: "Engineering",
};
const INDUSTRY_LABELS = {
  deftech: "Defense tech", govtech: "Gov tech", "gov-it": "Gov IT", space: "Space", ai: "AI",
  cybersecurity: "Cybersecurity", bigtech: "Big tech", saas: "Enterprise software",
  cspm: "Cloud security", finops: "FinOps", grc: "GRC", healthtech: "Health & bio",
  "american-dynamism": "American Dynamism", fintech: "Fintech", crypto: "Crypto",
  consumer: "Consumer", games: "Games",
};
const LOCATION_LABELS = {
  dmv_onsite: "On-site",
  dmv_hybrid: "Hybrid",
  remote_us: "Remote (US)",
  unknown: "Uncertain",
  other: "Other",
};
const LOCATION_TYPES = ["dmv_onsite", "dmv_hybrid", "remote_us", "unknown"];
const TAG_LABELS = { public_sector: "Public sector", clearance: "Clearance" };
const TAG_ORDER = ["public_sector", "clearance"];
// Industries sorted to the top by default ("mission first").
const MISSION_INDUSTRIES = ["deftech", "govtech", "gov-it", "space", "american-dynamism"];
const NEW_DAYS = 7;
const SELECTS = {
  role: "f-role", industry: "f-industry", level: "f-level", company: "f-company", sort: "f-sort",
};
const TOGGLES = { public_sector: "f-public_sector", clearance: "f-clearance" };

// umbrellas: selected categories (any-of). loc: selected location types (any-of).
const state = { jobs: [], meta: null, umbrellas: new Set(), loc: new Set(), view: "", umbrellaOrder: [] };
const $ = (id) => document.getElementById(id);

// Prod serves index.html at the site root with data/ as a sibling; local `http.server`
// serves it under /site/. Try both so either works.
async function loadJSON(name) {
  for (const base of ["./data/", "../data/"]) {
    try {
      const res = await fetch(base + name, { cache: "no-store" });
      if (res.ok) return await res.json();
    } catch (_) { /* try next */ }
  }
  return null;
}

function daysAgo(iso) {
  if (!iso) return Infinity;
  const then = new Date(iso.length === 10 ? iso + "T00:00:00Z" : iso).getTime();
  return (Date.now() - then) / 86400000;
}

function relativeDays(iso) {
  const d = Math.floor(daysAgo(iso));
  if (!Number.isFinite(d)) return "";
  if (d <= 0) return "today";
  if (d === 1) return "1d ago";
  if (d < 60) return `${d}d ago`;
  return `${Math.round(d / 30)}mo ago`;
}

function relativeTime(iso) {
  const hours = daysAgo(iso) * 24;
  if (!Number.isFinite(hours)) return "–";
  if (hours < 1) return "just now";
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

// Job URLs come from third-party ATS data. Only allow http(s) so a malicious posting
// can't smuggle a javascript:/data: URL into an href (DOM-based XSS on click).
function safeUrl(url) {
  try {
    const u = new URL(url, location.href);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : "#";
  } catch (_) {
    return "#";
  }
}

function taxonomy() {
  return (state.meta && state.meta.taxonomy) || { umbrellas: {}, tags: {} };
}
function umbrellaLabel(key) {
  return (taxonomy().umbrellas[key] || {}).label || UMBRELLA_LABELS[key] || key;
}
function roleLabels() {
  const out = {};
  Object.values(taxonomy().umbrellas).forEach((u) => Object.assign(out, u.roles || {}));
  return out;
}
function tagLabel(key) {
  return (taxonomy().tags || {})[key] || TAG_LABELS[key] || key;
}

// A multi-city posting's location string can be long; show the DMV city when there is one.
const DMV_HINT = /(washington,? d\.?c|district of columbia|virginia|, va\b|maryland|, md\b|reston|arlington|mcLean|herndon|bethesda|fort meade|springfield|alexandria)/i;
function shortLocation(job) {
  const parts = (job.location || "").split(/;\s*/).filter(Boolean);
  if (parts.length <= 1) return job.location || "";
  const pick = (job.location_type || "").startsWith("dmv") ? parts.find((p) => DMV_HINT.test(p)) : null;
  return `${pick || parts[0]} +${parts.length - 1} more`;
}

const ARROW = '<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M7 17 L17 7"></path><path d="M8 7 L17 7 L17 16"></path></svg>';

function card(job) {
  const article = el("article", "card");

  const top = el("div", "card-top");
  const head = el("div", "card-head");
  const h3 = el("h3");
  const a = el("a", null, job.title || "Untitled role");
  a.href = safeUrl(job.url);
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  h3.appendChild(a);
  head.appendChild(h3);

  const sub = el("span", "card-sub");
  sub.appendChild(el("span", "co", job.company || ""));
  const loc = shortLocation(job);
  if (loc) {
    sub.appendChild(document.createTextNode(" · "));
    const l = el("span", "loc-text", loc);
    if (loc !== job.location) l.title = job.location;
    sub.appendChild(l);
  }
  // "On-site" / "Hybrid" / "Remote (US)", unless the location text already says remote.
  const type = job.location_type;
  const saysRemote = /remote/i.test(loc);
  if (type && type !== "unknown" && !(type === "remote_us" && saysRemote)) {
    sub.appendChild(document.createTextNode(" · " + (LOCATION_LABELS[type] || type)));
  }
  head.appendChild(sub);
  top.appendChild(head);
  if (daysAgo(job.first_seen) <= NEW_DAYS) top.appendChild(el("span", "badge-new", "New"));
  article.appendChild(top);

  const pills = el("div", "pills");
  const cats = job.umbrellas || [];
  const cat = cats.find((u) => state.umbrellas.has(u)) || cats[0];
  if (cat) pills.appendChild(el("span", "pill", umbrellaLabel(cat)));
  if (job.level) pills.appendChild(el("span", "pill", LEVEL_LABELS[job.level] || job.level));
  if (type === "unknown") {
    const u = el("span", "pill pill-uncertain", "Location uncertain");
    u.title = "Listed as just \"Washington\": could be Washington, DC or Washington State.";
    pills.appendChild(u);
  }
  TAG_ORDER.filter((t) => (job.tags || []).includes(t)).forEach((t) =>
    pills.appendChild(el("span", `pill pill-${t}`, tagLabel(t))));
  article.appendChild(pills);

  const foot = el("div", "card-foot");
  foot.appendChild(el("span", "seen", job.first_seen ? `First seen ${relativeDays(job.first_seen)}` : ""));
  const view = el("span", "view-role");
  view.innerHTML = "View role" + ARROW; // static markup only
  foot.appendChild(view);
  article.appendChild(foot);
  return article;
}

// Dropdown options in alphabetical order of what the user sees (not the internal key).
function sortedByLabel(values, label = (v) => v) {
  return [...new Set(values.filter(Boolean))]
    .sort((a, b) => label(a).localeCompare(label(b), undefined, { sensitivity: "base" }));
}

function addOption(sel, value, label) {
  const o = el("option", null, label);
  o.value = value;
  sel.appendChild(o);
}

function populateFilters() {
  const umb = new Set();
  const inds = new Set();
  const levels = new Set();
  const companies = new Set();
  state.jobs.forEach((j) => {
    (j.umbrellas || []).forEach((u) => umb.add(u));
    (j.industries || []).forEach((i) => inds.add(i));
    if (j.level) levels.add(j.level);
    if (j.company) companies.add(j.company);
  });

  // Config order (taxonomy) first, then anything else present in the data.
  const ordered = Object.keys(taxonomy().umbrellas).filter((u) => umb.has(u));
  [...umb].sort().forEach((u) => { if (!ordered.includes(u)) ordered.push(u); });
  state.umbrellaOrder = ordered;
  const catChips = $("category-chips");
  ordered.forEach((u) => {
    const b = el("button", "chip", umbrellaLabel(u));
    b.type = "button";
    b.dataset.umbrella = u;
    b.setAttribute("aria-pressed", "false");
    catChips.appendChild(b);
  });
  const industryLabel = (i) => INDUSTRY_LABELS[i] || i;
  sortedByLabel([...inds], industryLabel).forEach((i) => addOption($("f-industry"), i, industryLabel(i)));
  LEVEL_ORDER.filter((l) => levels.has(l)).forEach((l) => addOption($("f-level"), l, LEVEL_LABELS[l]));
  sortedByLabel([...companies]).forEach((c) => addOption($("f-company"), c, c));
  populateRoles();

  // Only offer the "Washington (uncertain)" chip when such jobs exist.
  const chip = document.querySelector('.chip[data-loc="unknown"]');
  chip.hidden = !state.jobs.some((j) => j.location_type === "unknown");
}

// Role options follow the chosen categories (all roles when none is chosen).
function populateRoles() {
  const sel = $("f-role");
  const keep = sel.value;
  const labels = roleLabels();
  const allowed = new Set();
  state.umbrellas.forEach((u) =>
    Object.keys((taxonomy().umbrellas[u] || {}).roles || {}).forEach((r) => allowed.add(r)));
  const present = new Set();
  state.jobs.forEach((j) => {
    if (state.umbrellas.size && !(j.umbrellas || []).some((u) => state.umbrellas.has(u))) return;
    (j.roles || []).forEach((r) => { if (!allowed.size || allowed.has(r)) present.add(r); });
  });
  sel.length = 1; // keep the "All" option
  sortedByLabel([...present], (r) => labels[r] || r)
    .forEach((r) => addOption(sel, r, labels[r] || r));
  sel.value = present.has(keep) ? keep : "";
}

function currentFilters() {
  const f = { q: $("q").value.trim() };
  Object.entries(SELECTS).forEach(([k, id]) => { f[k] = $(id).value; });
  f.umbrella = state.umbrellaOrder.filter((u) => state.umbrellas.has(u)).join(",");
  f.loc = LOCATION_TYPES.filter((t) => state.loc.has(t)).join(",");
  Object.entries(TOGGLES).forEach(([k, id]) => { f[k] = $(id).getAttribute("aria-pressed") === "true"; });
  f.view = state.view;
  return f;
}

// "dmv" in a URL is shorthand for on-site + hybrid; "remote" for remote_us.
function parseLoc(value) {
  const out = new Set();
  (value || "").split(",").map((s) => s.trim()).forEach((v) => {
    if (v === "dmv") { out.add("dmv_onsite"); out.add("dmv_hybrid"); }
    else if (v === "remote") out.add("remote_us");
    else if (LOCATION_TYPES.includes(v)) out.add(v);
  });
  return out;
}

function urlLoc(set) {
  const s = new Set(set);
  const parts = [];
  if (s.has("dmv_onsite") && s.has("dmv_hybrid")) { parts.push("dmv"); s.delete("dmv_onsite"); s.delete("dmv_hybrid"); }
  if (s.has("remote_us")) { parts.push("remote"); s.delete("remote_us"); }
  return [...parts, ...LOCATION_TYPES.filter((t) => s.has(t))].join(",");
}

function matches(job, f) {
  if (f.q) {
    const q = f.q.toLowerCase();
    if (!(`${job.title} ${job.company}`.toLowerCase().includes(q))) return false;
  }
  if (state.umbrellas.size && !(job.umbrellas || []).some((u) => state.umbrellas.has(u))) return false;
  if (f.role && !(job.roles || []).includes(f.role)) return false;
  if (f.industry && !(job.industries || []).includes(f.industry)) return false;
  if (f.level && job.level !== f.level) return false;
  if (f.company && job.company !== f.company) return false;
  if (state.loc.size && !state.loc.has(job.location_type)) return false;
  if (f.public_sector && !(job.tags || []).includes("public_sector")) return false;
  if (f.clearance && !(job.tags || []).includes("clearance")) return false;
  return true;
}

function isMission(job) {
  return (job.industries || []).some((i) => MISSION_INDUSTRIES.includes(i));
}

// jobs.json arrives in priority order; both sorts are stable on top of it.
function sortJobs(jobs, sort) {
  const out = jobs.slice();
  if (sort === "new") {
    out.sort((a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""));
  } else {
    out.sort((a, b) => Number(isMission(b)) - Number(isMission(a)));
  }
  return out;
}

function syncURL(f) {
  const p = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => {
    if (k === "loc") { if (state.loc.size) p.set("loc", urlLoc(state.loc)); return; }
    if (v) p.set(k, v === true ? "1" : v);
  });
  const qs = p.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

function restoreFromURL() {
  const p = new URLSearchParams(location.search);
  if (p.get("q")) $("q").value = p.get("q");
  state.umbrellas = new Set((p.get("umbrella") || "").split(",")
    .map((s) => s.trim()).filter((u) => state.umbrellaOrder.includes(u)));
  populateRoles(); // role options depend on the categories
  Object.entries(SELECTS).forEach(([k, id]) => { if (p.get(k)) $(id).value = p.get(k); });
  Object.entries(TOGGLES).forEach(([k, id]) => {
    if (p.get(k)) $(id).setAttribute("aria-pressed", "true");
  });
  state.loc = parseLoc(p.get("loc") || (p.get("remote") ? "remote" : "")); // old links used ?remote=1
  state.view = p.get("view") === "list" ? "list" : "";
}

function syncControls() {
  document.querySelectorAll(".chip[data-umbrella]").forEach((b) =>
    b.setAttribute("aria-pressed", String(state.umbrellas.has(b.dataset.umbrella))));
  document.querySelectorAll(".chip[data-loc]").forEach((b) =>
    b.setAttribute("aria-pressed", String(state.loc.has(b.dataset.loc))));
  document.querySelectorAll(".view-toggle button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.view === state.view)));
  $("job-list").classList.toggle("list", state.view === "list");
}

function render() {
  const f = currentFilters();
  syncURL(f);
  syncControls();
  const list = $("job-list");
  list.replaceChildren();
  const filtered = sortJobs(state.jobs.filter((j) => matches(j, f)), f.sort);
  const frag = document.createDocumentFragment();
  filtered.forEach((j) => frag.appendChild(card(j)));
  list.appendChild(frag);
  $("empty").hidden = filtered.length > 0;
  $("empty-text").textContent = "No roles match these filters. Try removing one.";
  const companies = new Set(filtered.map((j) => j.company)).size;
  $("count").textContent =
    `Showing ${filtered.length.toLocaleString()} role${filtered.length === 1 ? "" : "s"} · ${companies} compan${companies === 1 ? "y" : "ies"}`;
}

function renderMeta() {
  $("stat-roles").textContent = state.jobs.length.toLocaleString();
  $("stat-companies").textContent = new Set(state.jobs.map((j) => j.company)).size.toLocaleString();
  if (!state.meta) { $("stat-updated-text").textContent = "Daily"; return; }
  const when = state.meta.generated_at;
  $("stat-updated-text").textContent = when ? relativeTime(when) : "Daily";
  const ok = (state.meta.adapters || []).filter((a) => a.ok).length;
  const total = (state.meta.adapters || []).length;
  const parts = [];
  if (when) parts.push(`Last updated ${when.slice(0, 10)}`);
  if (total) parts.push(`${ok}/${total} job boards OK`);
  $("meta").textContent = parts.join(" · ");
}

async function init() {
  const data = await loadJSON("jobs.json");
  state.meta = await loadJSON("meta.json");
  if (!data || !Array.isArray(data.jobs)) {
    $("count").textContent = "Couldn't load roles";
    $("empty").hidden = false;
    $("empty-text").textContent = "Couldn't load the job data. Try refreshing in a minute.";
    return;
  }
  state.jobs = data.jobs;

  populateFilters();
  restoreFromURL();
  renderMeta();
  render();

  $("q").addEventListener("input", render);
  Object.values(SELECTS).forEach((id) => $(id).addEventListener("change", render));
  document.querySelectorAll(".chip[data-umbrella]").forEach((b) => {
    b.addEventListener("click", () => {
      const u = b.dataset.umbrella;
      if (state.umbrellas.has(u)) state.umbrellas.delete(u); else state.umbrellas.add(u);
      populateRoles();
      render();
    });
  });
  Object.values(TOGGLES).forEach((id) => {
    $(id).addEventListener("click", (e) => {
      const b = e.currentTarget;
      b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
      render();
    });
  });
  document.querySelectorAll(".chip[data-loc]").forEach((b) => {
    b.addEventListener("click", () => {
      const t = b.dataset.loc;
      if (state.loc.has(t)) state.loc.delete(t); else state.loc.add(t);
      render();
    });
  });
  document.querySelectorAll(".view-toggle button").forEach((b) => {
    b.addEventListener("click", () => { state.view = b.dataset.view; render(); });
  });
  $("reset").addEventListener("click", () => {
    $("q").value = "";
    Object.values(SELECTS).forEach((id) => { $(id).value = ""; });
    Object.values(TOGGLES).forEach((id) => $(id).setAttribute("aria-pressed", "false"));
    state.loc.clear();
    state.umbrellas.clear();
    populateRoles();
    render();
  });
}

init();
