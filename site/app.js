// DMV Mission Jobs — reads data/jobs.json, renders + filters client-side. No build step.

const LEVEL_ORDER = ["intern", "junior", "mid", "senior", "staff", "principal", "lead", "manager", "director", "vp"];
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
const LOCATION_LABELS = {
  dmv_onsite: "dmv on-site",
  dmv_hybrid: "dmv hybrid",
  remote_us: "remote (us)",
  unknown: "washington?",
};
const TAG_LABELS = { public_sector: "public sector", clearance: "clearance" };
// Industries sorted to the top by default ("mission first").
const MISSION_INDUSTRIES = ["deftech", "govtech", "gov-it", "space"];
const NEW_DAYS = 7;
// Filter control ids -> URL param names. Checkbox params are "1" when on.
const SELECTS = {
  umbrella: "f-umbrella", role: "f-role", industry: "f-industry", level: "f-level",
  loc: "f-loc", company: "f-company", sort: "f-sort",
};
const CHECKBOXES = { public_sector: "f-public_sector", clearance: "f-clearance" };

const state = { jobs: [], meta: null };

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
  const then = new Date(iso + "T00:00:00Z").getTime();
  return (Date.now() - then) / 86400000;
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

function card(job) {
  const a = el("a", "job");
  a.href = safeUrl(job.url);
  a.target = "_blank";
  a.rel = "noopener noreferrer";

  const top = el("div", "job-top");
  const left = el("div");
  left.appendChild(el("span", "job-title", job.title || "Untitled role"));
  left.appendChild(document.createTextNode(" @ "));
  left.appendChild(el("span", "company", job.company || ""));
  top.appendChild(left);
  top.appendChild(el("span", "apply", "apply →"));
  a.appendChild(top);

  const meta = el("div", "job-meta");
  (job.tags || []).forEach((t) =>
    meta.appendChild(el("span", `tag ${t.replace(/_/g, "-")}`, taxonomy().tags[t] ? taxonomy().tags[t].toLowerCase() : (TAG_LABELS[t] || t))));
  if (job.level) meta.appendChild(el("span", "tag level", job.level));
  (job.industries || []).forEach((i) => meta.appendChild(el("span", "tag industry", i)));
  if (job.location) meta.appendChild(el("span", "tag", job.location));
  if (job.location_type) {
    meta.appendChild(el("span", `tag loc ${job.location_type}`, LOCATION_LABELS[job.location_type] || job.location_type));
  }
  if (daysAgo(job.first_seen) <= NEW_DAYS) meta.appendChild(el("span", "tag new", "new"));
  if (job.description_available === false) {
    meta.appendChild(el("span", "tag no-desc", "full description on company site"));
  }
  a.appendChild(meta);
  return a;
}

function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort();
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

  const umbSel = document.getElementById("f-umbrella");
  // Config order (taxonomy) first, then anything else present in the data.
  const ordered = Object.keys(taxonomy().umbrellas).filter((u) => umb.has(u));
  [...umb].sort().forEach((u) => { if (!ordered.includes(u)) ordered.push(u); });
  ordered.forEach((u) => {
    const o = el("option", null, umbrellaLabel(u));
    o.value = u;
    umbSel.appendChild(o);
  });
  populateRoles();
  const indSel = document.getElementById("f-industry");
  uniqueSorted([...inds]).forEach((i) => {
    const o = el("option", null, i); o.value = i; indSel.appendChild(o);
  });
  const lvlSel = document.getElementById("f-level");
  LEVEL_ORDER.filter((l) => levels.has(l)).forEach((l) => {
    const o = el("option", null, l); o.value = l; lvlSel.appendChild(o);
  });
  const coSel = document.getElementById("f-company");
  uniqueSorted([...companies]).forEach((c) => {
    const o = el("option", null, c); o.value = c; coSel.appendChild(o);
  });
}

// Role options follow the chosen category (all roles when no category is chosen).
function populateRoles() {
  const sel = document.getElementById("f-role");
  const keep = sel.value;
  const umbrella = document.getElementById("f-umbrella").value;
  const labels = roleLabels();
  const present = new Set();
  state.jobs.forEach((j) => {
    if (umbrella && !(j.umbrellas || []).includes(umbrella)) return;
    const allowed = umbrella ? Object.keys((taxonomy().umbrellas[umbrella] || {}).roles || {}) : null;
    (j.roles || []).forEach((r) => { if (!allowed || allowed.length === 0 || allowed.includes(r)) present.add(r); });
  });
  sel.length = 1; // keep the "all roles" option
  [...present].sort((a, b) => (labels[a] || a).localeCompare(labels[b] || b)).forEach((r) => {
    const o = el("option", null, labels[r] || r);
    o.value = r;
    sel.appendChild(o);
  });
  sel.value = present.has(keep) ? keep : "";
}

function currentFilters() {
  const f = { q: document.getElementById("q").value.trim().toLowerCase() };
  Object.entries(SELECTS).forEach(([k, id]) => { f[k] = document.getElementById(id).value; });
  Object.entries(CHECKBOXES).forEach(([k, id]) => { f[k] = document.getElementById(id).checked; });
  return f;
}

function matchesLocation(job, loc) {
  const t = job.location_type;
  if (!loc) return true;
  if (loc === "dmv") return t === "dmv_onsite" || t === "dmv_hybrid";
  if (loc === "remote") return t === "remote_us";
  return t === loc;
}

function matches(job, f) {
  if (f.q && !(`${job.title} ${job.company}`.toLowerCase().includes(f.q))) return false;
  if (f.umbrella && !(job.umbrellas || []).includes(f.umbrella)) return false;
  if (f.role && !(job.roles || []).includes(f.role)) return false;
  if (f.industry && !(job.industries || []).includes(f.industry)) return false;
  if (f.level && job.level !== f.level) return false;
  if (f.company && job.company !== f.company) return false;
  if (!matchesLocation(job, f.loc)) return false;
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
    if (v && v !== false) p.set(k, v === true ? "1" : v);
  });
  const qs = p.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

function restoreFromURL() {
  const p = new URLSearchParams(location.search);
  const set = (id, key) => { const v = p.get(key); if (v) document.getElementById(id).value = v; };
  set("q", "q");
  set(SELECTS.umbrella, "umbrella");
  populateRoles(); // role options depend on the category
  Object.entries(SELECTS).forEach(([k, id]) => { if (k !== "umbrella") set(id, k); });
  Object.entries(CHECKBOXES).forEach(([k, id]) => {
    if (p.get(k)) document.getElementById(id).checked = true;
  });
  // Old links used ?remote=1.
  if (p.get("remote") && !p.get("loc")) document.getElementById(SELECTS.loc).value = "remote";
}

function render() {
  const f = currentFilters();
  syncURL(f);
  const list = document.getElementById("job-list");
  list.innerHTML = "";
  const filtered = sortJobs(state.jobs.filter((j) => matches(j, f)), f.sort);
  filtered.forEach((j) => list.appendChild(card(j)));
  document.getElementById("empty").hidden = filtered.length > 0;
  document.getElementById("count").textContent =
    `${filtered.length} role${filtered.length === 1 ? "" : "s"} · ${new Set(filtered.map((j) => j.company)).size} companies`;
}

function renderMeta() {
  if (!state.meta) return;
  const when = state.meta.generated_at ? new Date(state.meta.generated_at) : null;
  const ok = (state.meta.adapters || []).filter((a) => a.ok).length;
  const total = (state.meta.adapters || []).length;
  const parts = [];
  if (when) parts.push(`last updated ${when.toISOString().slice(0, 10)}`);
  if (total) parts.push(`${ok}/${total} boards ok`);
  parts.push(`${state.jobs.length} roles tracked`);
  document.getElementById("meta").textContent = parts.join(" · ");
}

async function init() {
  const data = await loadJSON("jobs.json");
  state.meta = await loadJSON("meta.json");
  if (!data || !Array.isArray(data.jobs)) {
    document.getElementById("empty").hidden = false;
    document.getElementById("empty").textContent = "could not load jobs data.";
    return;
  }
  state.jobs = data.jobs;

  populateFilters();
  restoreFromURL();
  renderMeta();
  render();

  document.getElementById("q").addEventListener("input", render);
  [...Object.values(SELECTS), ...Object.values(CHECKBOXES)].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => {
      if (id === SELECTS.umbrella) populateRoles();
      render();
    });
  });
  document.getElementById("reset").addEventListener("click", () => {
    document.getElementById("q").value = "";
    Object.values(SELECTS).forEach((id) => { document.getElementById(id).value = ""; });
    Object.values(CHECKBOXES).forEach((id) => { document.getElementById(id).checked = false; });
    populateRoles();
    render();
  });
}

init();
