"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const unit = (value, suffix, digits = 1) =>
    typeof value === "number" && Number.isFinite(value)
      ? value.toLocaleString("fr-FR", {maximumFractionDigits: digits}) + suffix
      : "Non mesuré";
  const el = (tag, value, cls = "") => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = value;
    if (cls) node.className = cls;
    return node;
  };
  const verdict = {
    FULL_GPU: "Modèle entièrement sur GPU",
    PARTIAL_CPU_OFFLOAD: "GPU + CPU",
    CPU_ONLY: "CPU uniquement",
    PROMPT_TRUNCATED: "Contexte tronqué",
  };
  function showModel(model) {
    const article = el("article", undefined, "perf-model");
    article.append(el("h3", model.label));
    if (model.status !== "MEASURED") {
      article.append(el("p", "Aucune mesure enregistrée pour ce modèle.", "perf-empty"));
      return article;
    }
    const best = model.largest_full_gpu_context;
    const qualified = model.qualified_near_limit_context;
    article.append(el("p",
      best ? "Plus grand contexte déclaré FULL_GPU : " +
        best.toLocaleString("fr-FR") + " tokens (provisoire)." :
        "Aucun contexte entièrement sur GPU confirmé par ce rapport.",
      "perf-summary"));
    article.append(el("p",
      qualified ? "Essai à fort remplissage validé jusqu’à " +
        qualified.toLocaleString("fr-FR") + " tokens (non certifié sur Fedora)." :
        "Aucun contexte qualifié par un essai à fort remplissage.",
      "perf-muted"));
    const overflow = el("div", undefined, "perf-scroll");
    const table = el("table", undefined, "perf-table");
    const head = el("thead");
    const header = el("tr");
    for (const title of [
      "Contexte", "Placement", "VRAM du modèle", "Chargement",
      "Lecture du prompt", "Génération", "Remplissage"
    ]) header.append(el("th", title));
    head.append(header);
    table.append(head);
    const body = el("tbody");
    for (const row of model.results) {
      const tr = el("tr");
      const fields = [
        unit(row.context_tokens, " tokens", 0),
        verdict[row.verdict] || "Non vérifié",
        unit(row.resident_vram_gib, " Go"),
        unit(row.load_seconds, " s"),
        unit(row.prompt_tokens_per_second, " tokens/s"),
        unit(row.output_tokens_per_second, " tokens/s"),
        unit(row.prompt_fill_pct, " %"),
      ];
      for (const field of fields) tr.append(el("td", field));
      body.append(tr);
    }
    table.append(body);
    overflow.append(table);
    article.append(overflow);
    const note = el("p", undefined, "perf-muted");
    note.textContent = model.near_limit_requested
      ? "Mesure demandée près de la limite du contexte (90 % cible)."
      : "Mesure standard : environ 60 % du contexte, qualification provisoire.";
    article.append(note);
    return article;
  }
  async function load() {
    try {
      const response = await fetch("/api/performance", {cache: "no-store"});
      if (!response.ok) throw new Error("Rapport local non disponible");
      const data = await response.json();
      const messages = {
        NOT_MEASURED: "Aucune mesure enregistrée. Les modèles ne sont pas sollicités.",
        MEASURED: "Rapport local disponible. Mesures indicatives, non certifiées.",
        STALE: "Rapport de plus de 30 jours : mesures anciennes à requalifier.",
        UNVERIFIED: "Rapport invalide, insuffisamment protégé ou inaccessible : valeurs masquées.",
      };
      $("perf-status").textContent =
        messages[data.status] || "État du rapport indéterminé.";
      $("perf-status").classList.toggle("error", data.status === "UNVERIFIED");
      $("perf-date").textContent = data.recorded_at
        ? "Dernier relevé : " + new Date(data.recorded_at).toLocaleString("fr-FR")
        : "Aucune date de mesure validée.";
      $("perf-note").textContent = data.note || "";
      const models = $("perf-models");
      models.replaceChildren(...data.models.map(showModel));
    } catch (_error) {
      $("perf-status").textContent = "Lecture indisponible. Aucune mesure simulée.";
      $("perf-status").classList.add("error");
      $("perf-date").textContent = "";
      $("perf-models").replaceChildren();
    }
  }
  load();
})();
