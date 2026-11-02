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

// 1. Open A then B; answers arrive B first, then A. Only B may be drawn and approved.
await reset();
context.loadProject("alpha"); await settle();
context.loadProject("beta"); await settle();
pendingCloud.get("beta")(reply(true, cloudInfo)); await settle();
pendingCloud.get("alpha")(reply(true, cloudInfo)); await settle();
check(box().text.includes("Projet Beta"), "le panneau cloud doit nommer le projet ouvert (Beta)");
check(!box().text.includes("Projet Alpha"), "une réponse tardive de A ne doit rien afficher dans B");
const approves = [];
box().find((el) => { if (el.textContent === "Autoriser le cloud pour ce projet") approves.push(el); return false; });
check(approves.length === 1, `un seul bouton d’accord attendu, ${approves.length} trouvé(s)`);
const ack = box().find((el) => el.id === "cloud-ack");
if (ack && approves.length) {
  ack.checked = true; ack.dispatch("change");
  approves[approves.length - 1].dispatch("click"); await settle();
}
const approvals = posts.filter((p) => p.path === "/api/cloud-approve");
check(approvals.length === 1 && approvals[0].body.project_id === "beta",
  "l’accord doit viser beta uniquement: " + JSON.stringify(approvals));

// 2. A control kept from A and clicked after B was opened sends nothing.
await reset();
context.loadProject("alpha"); await settle();
pendingCloud.get("alpha")(reply(true, cloudInfo)); await settle();
const staleAck = box().find((el) => el.id === "cloud-ack");
const staleApprove = box().find((el) => el.textContent === "Autoriser le cloud pour ce projet");
context.loadProject("beta"); await settle();
if (staleAck && staleApprove) {
  staleAck.checked = true; staleAck.dispatch("change");
  staleApprove.dispatch("click"); await settle();
} else failures.push("contrôles cloud de A introuvables");
check(posts.filter((p) => p.path.startsWith("/api/cloud-")).length === 0,
  "un contrôle périmé ne doit envoyer aucun accord: " + JSON.stringify(posts));
check(document.getElementById("message").textContent.includes("autre projet"),
  "l’utilisateur doit être averti que le contrôle est périmé");

// 3. A stale revoke (project already approved) sends nothing either.
await reset();
context.loadProject("alpha"); await settle();
pendingCloud.get("alpha")(reply(true, { ...cloudInfo, state: "approved" })); await settle();
const staleRevoke = box().find((el) => el.textContent.startsWith("Retirer l’accord cloud"));
context.loadProject("beta"); await settle();
if (staleRevoke) { staleRevoke.dispatch("click"); await settle(); }
else failures.push("bouton de retrait de A introuvable");
check(posts.length === 0, "un retrait périmé ne doit rien envoyer: " + JSON.stringify(posts));

// 4. A late error for A is not shown inside B.
await reset();
context.loadProject("alpha"); await settle();
context.loadProject("beta"); await settle();
pendingCloud.get("beta")(reply(true, cloudInfo)); await settle();
pendingCloud.get("alpha")(reply(false, { error: "panne simulée" })); await settle();
check(!box().text.includes("panne simulée"), "une erreur tardive de A ne doit pas apparaître dans B");

if (failures.length) {
  console.error(failures.map((f) => "ÉCHEC: " + f).join("\n"));
  process.exit(1);
}
console.log("DASHBOARD_CLOUD_RACE=PASS");
