"use strict";

/* Read-only inventory followed by an exact, one-shot approval for a caption/cell.
 * Neither credentials nor signed image download URLs enter this browser. */
(() => {
  const $ = (id) => document.getElementById(id);
  let page = null;
  let details = null;
  let plan = null;

  function notice(message, error = false) {
    const target = $("notion-status");
    target.textContent = message;
    target.classList.toggle("error", error);
  }
  function appendText(tag, value, parent) {
    const element = document.createElement(tag);
    element.textContent = value;
    parent.append(element);
    return element;
  }
  async function post(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const json = await response.json();
    if (!response.ok) throw new Error(json.error || "Requête Notion refusée");
    return json;
  }
  async function act(button, action) {
    button.disabled = true;
    try {
      notice("");
      await action();
    } catch (error) {
      notice(error.message || "Action impossible", true);
    } finally {
      button.disabled = false;
    }
  }
  function clearApproval() {
    plan = null;
    $("media-diff-panel").hidden = true;
    $("media-apply-form").hidden = true;
    $("media-result").textContent = "";
    $("media-approve-page").value = "";
    $("media-approve-manifest").value = "";
    $("media-approve-human").checked = false;
  }
  function clearDetails() {
    details = null;
    $("media-structure").replaceChildren();
    $("media-plan-form").hidden = true;
    $("media-row-fields").hidden = true;
    $("media-row").replaceChildren();
    $("media-cell").replaceChildren();
    $("media-segment").replaceChildren();
    $("media-new-text").value = "";
    clearApproval();
  }
  function cellSegments() {
    if (!details) return [];
    if (details.kind === "image") return details.segments;
    const row = details.rows.find((entry) => entry.row_id === $("media-row").value);
    const column = Number($("media-cell").value);
    return row?.cells[column] || [];
  }
  function chooseSegment() {
    clearApproval();
    const choices = $("media-segment");
    choices.replaceChildren();
    const segments = cellSegments();
    for (const segment of segments) {
      if (!segment.editable) continue;
      const option = document.createElement("option");
      option.value = String(segment.index);
      option.textContent = "Segment " + segment.index +
        (segment.empty ? " · Vide" : " · " + segment.text.slice(0, 95));
      choices.append(option);
    }
    const selected = segments.find((part) => part.index === Number(choices.value));
    $("media-new-text").value = selected?.text || "";
    $("media-plan-form").hidden = choices.options.length === 0;
    if (!choices.options.length) {
      notice("Cellule ou légende non éditable : segments avec liens ou objets inconnus.", true);
    }
  }
  function renderTable(result) {
    const parent = $("media-structure");
    appendText("p", result.rows.length + " lignes × " +
      result.width + " colonnes ; texte uniquement, aucun changement de structure.", parent);
    const wrap = appendText("div", "", parent);
    wrap.className = "media-table-scroll";
    const table = document.createElement("table");
    table.className = "media-table";
    for (const [rowIndex, entry] of result.rows.entries()) {
      const tr = document.createElement("tr");
      for (const segments of entry.cells) {
        const tag = rowIndex === 0 ? "th" : "td";
        appendText(tag, segments.map((item) => item.text).join("") || "—", tr);
      }
      table.append(tr);
    }
    wrap.append(table);
  }
  function renderImage(result) {
    const parent = $("media-structure");
    appendText("p", "Image existante : seul le texte de légende est modifiable.", parent);
    for (const segment of result.segments) {
      appendText("p", "Segment " + segment.index + " : " +
        (segment.text || "Légende vide"), parent);
    }
  }
  function populateTable(result) {
    const rowSelect = $("media-row");
    const columnSelect = $("media-cell");
    $("media-row-fields").hidden = false;
    result.rows.forEach((row, i) => {
      const option = document.createElement("option");
      option.value = row.row_id;
      option.textContent = "Ligne " + (i + 1);
      rowSelect.append(option);
    });
    for (let index = 0; index < result.width; index++) {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = "Colonne " + (index + 1);
      columnSelect.append(option);
    }
  }

  window.addEventListener("notion:page", (event) => {
    page = event.detail;
    clearDetails();
    const select = $("media-block");
    select.replaceChildren();
    const candidates = (page?.blocks || []).filter((block) => block.media_candidate);
    for (const block of candidates) {
      const option = document.createElement("option");
      option.value = block.block_id;
      option.textContent = (block.type === "image" ? "Image" : "Tableau") +
        " · " + block.block_id.slice(0, 12);
      select.append(option);
    }
    select.disabled = candidates.length === 0;
    $("media-read").disabled = candidates.length === 0;
  });
  $("media-block").addEventListener("change", clearDetails);
  $("media-row").addEventListener("change", chooseSegment);
  $("media-cell").addEventListener("change", chooseSegment);
  $("media-segment").addEventListener("change", () => {
    clearApproval();
    const segment = cellSegments().find((item) =>
      item.index === Number($("media-segment").value));
    $("media-new-text").value = segment?.text || "";
  });
  $("media-new-text").addEventListener("input", clearApproval);
  $("media-select-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await act($("media-read"), async () => {
      if (!page) throw new Error("Examiner d'abord une page Notion.");
      clearDetails();
      const result = await post("/api/notion/media-inspect", {
        page: page.page_id, block_id: $("media-block").value,
      });
      details = result;
      if (result.kind === "table") {
        populateTable(result);
        renderTable(result);
      } else {
        renderImage(result);
      }
      chooseSegment();
      notice("Contenu consulté. Aucune écriture Notion.");
    });
  });
  $("media-plan-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await act($("media-plan-button"), async () => {
      if (!details) throw new Error("Relire le tableau ou l'image d'abord.");
      clearApproval();
      const result = await post("/api/notion/media-plan", {
        page: details.page_id,
        block_id: details.block_id,
        row_id: details.kind === "table" ? $("media-row").value : null,
        cell_index: details.kind === "table" ? Number($("media-cell").value) : null,
        segment_index: Number($("media-segment").value),
        text: $("media-new-text").value,
      });
      plan = {
        id: result.plan_id, page: result.page_id,
        digest: result.manifest_sha256,
      };
      $("media-diff").textContent = result.diff;
      $("media-digest").textContent = result.manifest_sha256;
      $("media-diff-panel").hidden = false;
      $("media-apply-form").hidden = false;
      notice("Plan préparé sans écriture : relire le diff avant d'approuver.");
    });
  });
  $("media-apply-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await act($("media-apply-form").querySelector("button[type=submit]"), async () => {
      if (!plan) throw new Error("Nouveau plan requis.");
      const approval = {
        plan_id: plan.id, page: plan.page,
        approve_page: $("media-approve-page").value.trim(),
        approve_manifest: $("media-approve-manifest").value.trim(),
        human_approved: $("media-approve-human").checked,
      };
      // PATCH may have succeeded even if the connection fails. No implicit retry.
      clearApproval();
      const result = await post("/api/notion/media-apply", approval);
      $("media-result").textContent = JSON.stringify(result, null, 2);
      notice("Résultat relu via API. Vérifier le rendu natif Notion avant toute suite.");
    });
  });
})();
