"use strict";

/* The browser never receives Notion API tokens or filesystem paths.
 * Every remote write requires a separate explicit human action. */
const byId = (name) => document.getElementById(name);
let inventory = null;
let plan = null;

function status(text, error = false) {
  const target = byId("notion-status");
  target.textContent = text;
  target.classList.toggle("error", error);
}
function clearPlan() {
  plan = null;
  byId("diff-panel").hidden = true;
  byId("apply-form").hidden = true;
  byId("no-plan").hidden = false;
  byId("apply-result").textContent = "";
  byId("approve-human").checked = false;
  byId("approve-page").value = "";
  byId("approve-manifest").value = "";
}
function clearInventory() {
  inventory = null;
  byId("page-overview").hidden = true;
  byId("block-inventory").replaceChildren();
  byId("editors").replaceChildren();
  byId("add-edit").disabled = true;
  byId("plan-button").disabled = true;
  clearPlan();
}
async function post(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Opération refusée");
  return body;
}
async function submit(button, fn) {
  button.disabled = true;
  try {
    status("");
    await fn();
  } catch (error) {
    status(error.message || "Opération impossible", true);
  } finally {
    button.disabled = false;
  }
}
function appendText(tag, text, parent, className = "") {
  const item = document.createElement(tag);
  item.textContent = text;
  if (className) item.className = className;
  parent.append(item);
  return item;
}
function fields() {
  const editors = [...byId("editors").querySelectorAll(".editor")];
  return editors.map((container) => ({
    block_id: container.querySelector("select").value,
    text: container.querySelector("textarea").value,
  }));
}
function setCounts() {
  const count = byId("editors").querySelectorAll(".editor").length;
  byId("add-edit").disabled = !inventory || count >= 5 ||
    count >= inventory.blocks.filter((b) => b.eligible).length;
  byId("plan-button").disabled = !inventory || count < 1;
}
function selectOptions(select, chosen) {
  for (const block of inventory.blocks.filter((b) => b.eligible)) {
    const option = document.createElement("option");
    option.value = block.block_id;
    option.textContent = block.type + " · " + (block.excerpt || block.block_id).slice(0, 100);
    select.append(option);
  }
  select.value = chosen;
}
function addEditor() {
  if (!inventory) return;
  const selected = fields().map((item) => item.block_id);
  const choice = inventory.blocks.find((item) => item.eligible && !selected.includes(item.block_id));
  if (!choice) return;
  const box = document.createElement("div");
  box.className = "editor";
  const header = document.createElement("div");
  header.className = "editor-header";
  appendText("strong", "Bloc à corriger", header);
  const remove = appendText("button", "Retirer", header);
  remove.type = "button";
  remove.className = "secondary";
  remove.addEventListener("click", () => {
    box.remove();
    clearPlan();
    setCounts();
  });
  box.append(header);
  const label = appendText("label", "Sélectionner un bloc textuel", box);
  const select = document.createElement("select");
  select.required = true;
  selectOptions(select, choice.block_id);
  label.append(select);
  const textareaLabel = appendText("label", "Texte complet de remplacement", box);
  const textarea = document.createElement("textarea");
  textarea.required = true;
  textarea.maxLength = 1900;
  textarea.rows = 4;
  textarea.placeholder = "Texte relu par le rédacteur et l'auditeur…";
  textareaLabel.append(textarea);
  const excerpt = appendText("p", "Texte actuel : " + (choice.excerpt || "—"), box, "current-excerpt");
  select.addEventListener("change", () => {
    const chosen = inventory.blocks.find((b) => b.block_id === select.value);
    excerpt.textContent = "Texte actuel : " + (chosen?.excerpt || "—");
    clearPlan();
  });
  select.addEventListener("input", clearPlan);
  textarea.addEventListener("input", clearPlan);
  byId("editors").append(box);
  clearPlan();
  setCounts();
}
byId("notion-page").addEventListener("input", clearInventory);
byId("add-edit").addEventListener("click", addEditor);

byId("inspect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await submit(byId("inspect-form").querySelector("button"), async () => {
    const page = byId("notion-page").value.trim();
    clearInventory();
    const result = await post("/api/notion/inspect", { page });
    inventory = result;
    byId("page-overview").hidden = false;
    byId("block-totals").textContent =
      result.editable_count + " blocs textuels candidats · " +
      result.protected_count + " blocs protégés";
    byId("inventory-short").textContent =
      "Empreinte de structure : " + result.inventory_sha256.slice(0, 12) + "…";
    const target = byId("block-inventory");
    for (const item of result.blocks) {
      const row = document.createElement("div");
      row.className = "inventory-item";
      appendText("span", item.eligible ? "Texte" : "Protégé", row,
        item.eligible ? "eligible" : "protected");
      appendText("span", item.type + " · " + (item.excerpt || item.block_id).slice(0, 115), row);
      target.append(row);
    }
    if (result.editable_count) addEditor();
    status("Lecture de la page terminée. Aucune écriture Notion.");
  });
});

byId("plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await submit(byId("plan-button"), async () => {
    if (!inventory) throw new Error("Examiner une page avant de proposer.");
    const edits = fields();
    if (!edits.length || edits.length > 5 ||
        new Set(edits.map((x) => x.block_id)).size !== edits.length) {
      throw new Error("Sélectionner entre un et cinq blocs distincts.");
    }
    clearPlan();
    const result = await post("/api/notion/plan", {
      page: inventory.page_id, edits,
    });
    plan = { id: result.plan_id, page: result.page_id, sha: result.manifest_sha256 };
    byId("diff-panel").hidden = false;
    const list = byId("diff-list");
    list.replaceChildren();
    for (const diff of result.edits) {
      const section = document.createElement("article");
      section.className = "diff-item";
      appendText("h4", "Bloc " + diff.block_id, section);
      appendText("pre", diff.diff, section);
      list.append(section);
    }
    byId("plan-digest").textContent = result.manifest_sha256;
    byId("apply-form").hidden = false;
    byId("no-plan").hidden = true;
    status("Prévisualisation créée. Aucun bloc n'a encore été modifié.");
  });
});

byId("apply-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await submit(byId("apply-form").querySelector("button[type=submit]"), async () => {
    if (!plan) throw new Error("Plan périmé : refaire l'aperçu.");
    const value = plan;
    // Even a network error can mean a remote PATCH succeeded. Require inspection.
    clearPlan();
    const result = await post("/api/notion/apply", {
      plan_id: value.id, page: value.page,
      approve_page: byId("approve-page").value.trim(),
      approve_manifest: byId("approve-manifest").value.trim(),
      human_approved: byId("approve-human").checked,
    });
    byId("apply-result").textContent = JSON.stringify(result, null, 2);
    status("Blocs relus après modification. Ouvrir Notion pour vérifier le rendu réel.");
  });
});
