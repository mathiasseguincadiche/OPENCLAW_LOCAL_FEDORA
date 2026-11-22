// Regression harness for A03: runs the real dashboard.js in a minimal DOM with controlled API
// answers. No browser, network or model: every fetch is answered by this file.
// Usage: node tests/js/dashboard_cloud_race.mjs path/to/dashboard.js
import { readFileSync } from "node:fs";
import vm from "node:vm";

class FakeElement {
  constructor(tag, id = "") {
    Object.assign(this, { tag, id, children: [], listeners: {}, dataset: {}, textContent: "" });
    Object.assign(this, { value: "", hidden: false, disabled: false, checked: false, type: "" });
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  // Handlers are started, not awaited: an approval reloads the panel, whose answer the
  // scenario may deliberately leave pending. Callers wait with settle().
  dispatch(type) {
    for (const fn of this.listeners[type] || []) fn({ preventDefault() {}, target: this });
  }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  replaceChildren(...nodes) { this.children = [...nodes]; }
  remove() {}
  reset() {}
  setAttribute() {}
  querySelector() { return null; }
  get text() { return [this.textContent, ...this.children.map((c) => c.text ?? c.textContent ?? "")].join(" "); }
  find(predicate) {
    for (const child of this.children) {
      if (!(child instanceof FakeElement)) continue;
      if (predicate(child)) return child;
      const found = child.find(predicate);
      if (found) return found;
    }
    return null;
  }
}

const elements = new Map();
const document = {
  hidden: false,
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new FakeElement("div", id));
    return elements.get(id);
  },
  createElement: (tag) => new FakeElement(tag),
  createTextNode: (text) => ({ textContent: text }),
  addEventListener() {},
  querySelectorAll: () => [],
};

const posts = [];
const pendingCloud = new Map();
const titles = { alpha: "Projet Alpha", beta: "Projet Beta" };
const reply = (ok, value) => ({ ok, json: async () => value });
function fetch(path, options = {}) {
  const url = new URL(path, "http://127.0.0.1");
  if (options.method === "POST") {
    posts.push({ path: url.pathname, body: JSON.parse(options.body) });
    return Promise.resolve(reply(true, { ok: true }));
  }
  const project = url.searchParams.get("project");
  if (url.pathname === "/api/project")
    return Promise.resolve(reply(true, {
      manifest: { title: titles[project], status: "INTAKE_READY" },
      next_step: "", files: [], clarifications: { items: [] }, draft: null,
    }));
  if (url.pathname === "/api/cloud")
    return new Promise((resolve) => pendingCloud.set(project, resolve));
  // Status is not needed here: an error keeps refresh() and the mentor panel inert.
  return Promise.resolve(reply(false, { error: "statut simulé indisponible" }));
}

const context = vm.createContext({
  document, fetch, URL, URLSearchParams, console,
  setInterval: () => 0, clearInterval() {}, setTimeout, clearTimeout,
});
vm.runInContext(readFileSync(process.argv[2], "utf8"), context, { filename: "dashboard.js" });

const settle = async () => { for (let i = 0; i < 20; i++) await new Promise((r) => setImmediate(r)); };
const cloudInfo = { state: "none", consent_text: "Texte d’accord simulé.", models: {} };
const box = () => document.getElementById("cloud");
const failures = [];
const check = (condition, message) => { if (!condition) failures.push(message); };
const reset = async () => {
  posts.length = 0; pendingCloud.clear(); box().replaceChildren();
  document.getElementById("message").textContent = "";
};

// Retired cloud actions must stay absent even when a user switches projects rapidly.
await reset();
context.loadProject("alpha"); await settle();
context.loadProject("beta"); await settle();
check(pendingCloud.size === 0, "local-only dashboard must never request /api/cloud");
check(posts.every((p) => !p.path.startsWith("/api/cloud")), "no cloud approval/revoke POST");
check(box().children.length === 0, "no cloud approval panel may be rendered");
check(document.getElementById("message").textContent !== "panne simulée", "no retired cloud error");
// Repeat after navigation to ensure no deferred cloud request reappears.
context.loadProject("alpha"); await settle();
check(pendingCloud.size === 0, "project switch triggered an obsolete cloud request");
check(posts.every((p) => !p.path.startsWith("/api/cloud")), "project switch triggered cloud mutation");
if (failures.length) {
  console.error(failures.map((f) => "ÉCHEC: " + f).join("\\n"));
  process.exit(1);
}
console.log("DASHBOARD_CLOUD_RACE=PASS");
