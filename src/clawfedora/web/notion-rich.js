"use strict";

/* Separate local-only rich editor. Never place Notion tokens or paths in the DOM. */
(() => {
  const $ = (id) => document.getElementById(id);
  let page = null;
  let inspected = null;
  let pending = null;

  function message(text, error = false) {
    const el = $("notion-status");
    el.textContent = text;
    el.classList.toggle("error", error);
  }
  function resetApproval() {
    pending = null;
    $("rich-diff-panel").hidden = true;
    $("rich-apply-form").hidden = true;
    $("rich-result").textContent = "";
    $("rich-approve-page").value = "";
    $("rich-approve-manifest").value = "";
    $("rich-approve-human").checked = false;
  }
  function resetDetails() {
    inspected = null;
    $("rich-plan-form").hidden = true;
    $("rich-segments").replaceChildren();
    $("rich-segment").replaceChildren();
    $("rich-text").value = "";
    resetApproval();
  }
  function text(tag, value, parent) {
    const el = document.createElement(tag);
    el.textContent = value;
    parent.append(el);
    return el;
  }
  async function api(path, data) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || "Notion : action refusée");
    return value;
  }
  async function clicked(button, action) {
    button.disabled = true;
    try {
      message("");
      await action();
    } catch (error) {
      message(error.message || "Opération refusée", true);
    } finally {
      button.disabled = false;
    }
  }
  window.addEventListener("notion:page", (event) => {
    page = event.detail;
    resetDetails();
    const select = $("rich-block");
    select.replaceChildren();
    const candidates = (page?.blocks || []).filter((row) => row.rich_candidate);
    for (const row of candidates) {
      const option = document.createElement("option");
      option.value = row.block_id;
      option.textContent = row.type + " · " + (row.excerpt || row.block_id).slice(0, 100);
      select.append(option);
    }
    select.disabled = candidates.length === 0;
    $("rich-read").disabled = candidates.length === 0;
  });

  $("rich-block").addEventListener("change", resetDetails);
  $("rich-select-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await clicked($("rich-read"), async () => {
      if (!page) throw new Error("Commencer par examiner une page Notion.");
      resetDetails();
      const details = await api("/api/notion/rich-segments", {
        page: page.page_id, block_id: $("rich-block").value,
      });
      inspected = details;
      const options = $("rich-segment");
      for (const segment of details.segments) {
        const label = document.createElement("div");
        label.className = "inventory-item";
        text("span", segment.editable ? "Éditable" : "Lien", label);
        const formatted = Object.entries(segment.annotations)
          .filter(([key, value]) => value === true && key !== "color")
          .map(([key]) => key);
        text("span", "Segment " + segment.index + " : " +
          segment.text.slice(0, 130) +
          (formatted.length ? " · " + formatted.join(", ") : "") +
          (segment.annotations.color !== "default" ?
            " · " + segment.annotations.color : ""), label);
        $("rich-segments").append(label);
        if (segment.editable) {
          const option = document.createElement("option");
          option.value = String(segment.index);
          option.textContent = "Segment " + segment.index + " · " +
            segment.text.slice(0, 95);
          options.append(option);
        }
      }
      if (!options.options.length) throw new Error("Tous les segments portent des liens.");
      $("rich-plan-form").hidden = false;
      const current = details.segments.find((item) =>
        item.index === Number(options.value));
      $("rich-text").value = current?.text || "";
      message("Segments lus sans écriture. Choisir un segment et modifier uniquement son texte.");
    });
  });

  $("rich-segment").addEventListener("change", () => {
    resetApproval();
    const current = inspected?.segments.find((row) =>
      row.index === Number($("rich-segment").value));
    $("rich-text").value = current?.text || "";
  });
  $("rich-text").addEventListener("input", resetApproval);
  $("rich-plan-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await clicked($("rich-plan-button"), async () => {
      if (!page || !inspected) throw new Error("Relire les segments avant de proposer.");
      resetApproval();
      const result = await api("/api/notion/rich-plan", {
        page: inspected.page_id,
        block_id: inspected.block_id,
        segment_index: Number($("rich-segment").value),
        text: $("rich-text").value,
      });
      pending = {
        id: result.plan_id, page: result.page_id, sha: result.manifest_sha256,
      };
      $("rich-diff").textContent = result.diff;
      $("rich-digest").textContent = result.manifest_sha256;
      $("rich-preserved").textContent = result.preserved_segments +
        " autre(s) segment(s) conservé(s) à l’identique, annotations comprises.";
      $("rich-diff-panel").hidden = false;
      $("rich-apply-form").hidden = false;
      message("Plan enrichi préparé. Aucune écriture Notion.");
    });
  });
  $("rich-apply-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await clicked($("rich-apply-form").querySelector("button[type=submit]"), async () => {
      if (!pending) throw new Error("Nouvel aperçu requis.");
      const approval = {
        plan_id: pending.id,
        page: pending.page,
        approve_page: $("rich-approve-page").value.trim(),
        approve_manifest: $("rich-approve-manifest").value.trim(),
        human_approved: $("rich-approve-human").checked,
      };
      // The remote operation might succeed even if the connection times out.
      resetApproval();
      const result = await api("/api/notion/rich-apply", approval);
      $("rich-result").textContent = JSON.stringify(result, null, 2);
      message("Texte et styles relus via l'API. Vérifier le rendu réel dans Notion.");
    });
  });
})();
