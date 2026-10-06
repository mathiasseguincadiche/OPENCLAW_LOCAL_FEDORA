"use strict";
const $ = (id) => document.getElementById(id);
const states = {
  INTAKE_READY: "Documents reçus",
  ANALYZED: "Demande analysée",
  CLARIFICATION_REQUIRED: "Précisions attendues",
  PLANNED: "Plan préparé",
  ASSIGNED: "Prêt à travailler",
  IN_PROGRESS: "Travail en cours",
  VALIDATING: "Validation attendue",
  REVIEW: "Relecture attendue",
  PACKAGING: "Livraison en préparation",
  COMPLETE: "Terminé",
};
const phases = {
  preparing: "Préparation et recherche documentaire",
  running: "Une spécialité travaille",
  paused: "Travail en pause",
  failed: "Une tâche demande votre attention",
  awaiting_validation: "Livrables prêts pour la validation",
  reviewing: "L’auditeur examine les livrables",
  reviewed: "Audit enregistré",
  interrupted: "Travail interrompu — reprise possible",
};
const gib = (n) =>
  (n / 1073741824).toLocaleString("fr-FR", { maximumFractionDigits: 1 }) +
  " Go";
function node(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}
async function api(path, data) {
  const options = data
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }
    : {};
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Action indisponible");
  return result;
}
function tell(text, bad = false) {
  $("message").textContent = text;
  $("message").classList.toggle("error", bad);
}
async function action(path, data) {
  try {
    tell("");
    const value = await api(path, data);
    await refresh();
    return value;
  } catch (error) {
    tell(error.message, true);
    return null;
  }
}
async function refresh() {
  if (document.hidden) return;
  try {
    const data = await api("/api/status");
    $("profile").textContent =
      data.profile === "gaming" ? "Mode jeu" : "Profil quotidien";
    $("ram").textContent = data.memory.MemTotal
      ? gib(data.memory.MemTotal - data.memory.MemAvailable) +
        " / " +
        gib(data.memory.MemTotal)
      : "Mesure indisponible";
    $("vram").textContent = data.ollama_available
      ? gib(data.models.reduce((n, m) => n + m.size_vram, 0))
      : "Ollama arrêté";
    $("model").textContent =
      data.models.map((m) => m.name).join(", ") || "Aucun modèle chargé";
    const worker = data.worker;
    $("activity").textContent =
      (phases[worker.phase] || "Aucun travail actif") +
      (worker.active && worker.task_id ? " · " + worker.task_id : "");
    $("services").textContent =
      "Ollama : " +
      (data.ollama_available ? "disponible" : "arrêté") +
      " · OpenClaw : " +
      (data.gateway_available ? "port accessible" : "arrêté") +
      " · Versions prévues : " +
      data.versions.openclaw +
      " / " +
      data.versions.ollama;
    const selected = $("selected").value;
    $("projects").replaceChildren();
    $("selected").replaceChildren();
    for (const project of data.projects) {
      const option = node("option", project.title);
      option.value = project.project_id;
      $("selected").append(option);
      const row = node("article", undefined, "project"),
        detail = node("div"),
        buttons = node("div", undefined, "buttons");
      detail.append(
        node("h3", project.title),
        node(
          "p",
          (states[project.status] || project.status) +
            " · " +
            project.completed +
            " / " +
            project.total +
            " tâches" +
            (project.paused ? " · Pause demandée" : ""),
        ),
      );
      if (project.total) {
        const bar = node("progress");
        bar.max = project.total;
        bar.value = project.completed;
        bar.setAttribute("aria-label", "Tâches terminées");
        detail.append(bar);
      }
      if (data.errors[project.project_id])
        detail.append(node("p", data.errors[project.project_id], "error"));
      const pause = node("button", "Mettre en pause", "secondary"),
        resume = node(
          "button",
          project.paused ? "Reprendre" : "Démarrer / reprendre",
        );
      pause.disabled =
        !["ASSIGNED", "IN_PROGRESS"].includes(project.status) || project.paused;
      resume.disabled =
        worker.active ||
        data.profile === "gaming" ||
        !["ASSIGNED", "IN_PROGRESS"].includes(project.status);
      pause.addEventListener("click", () =>
        action("/api/pause", { project_id: project.project_id }),
      );
      resume.addEventListener("click", () =>
        action("/api/resume", { project_id: project.project_id }),
      );
      buttons.append(pause, resume);
      row.append(detail, buttons);
      $("projects").append(row);
    }
    if (data.projects.some((p) => p.project_id === selected))
      $("selected").value = selected;
    if (!data.projects.length)
      $("projects").append(
        node(
          "p",
          "Aucun projet pour le moment. Créez un projet et préparez son plan pour commencer.",
        ),
      );
  } catch (error) {
    tell("Connexion interrompue : " + error.message, true);
  }
}
$("index").addEventListener("click", async () => {
  if (!$("selected").value) return;
  const report = await action("/api/index", {
    project_id: $("selected").value,
  });
  if (report)
    tell(
      report.documents +
        " documents indexés, " +
        report.skipped.length +
        " documents non indexés.",
      report.skipped.length > 0,
    );
});
$("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("hits").replaceChildren();
  if (!$("selected").value) return;
  try {
    const hits = await api(
      "/api/search?" +
        new URLSearchParams({
          project: $("selected").value,
          q: $("query").value,
        }),
    );
    if (!hits.length)
      $("hits").append(
        node(
          "p",
          "Aucun passage trouvé. Actualisez l’index ou essayez d’autres mots.",
        ),
      );
    for (const hit of hits) {
      const article = node("article", undefined, "hit");
      const isNote = ["decision", "research"].includes(hit.kind);
      const title = hit.title || hit.path.replace(/^(intake|sources)\//, "");
      const location = isNote
        ? ""
        : (hit.kind === "pdf" || hit.path.endsWith(".pdf")
            ? " · page " + hit.page
            : "") +
          " · ligne " +
          hit.line;
      article.append(
        node(
          "p",
          title + location + (hit.stale ? " · Source à actualiser" : ""),
        ),
        node("pre", hit.text),
      );
      for (const source of hit.sources) {
        try {
          const url = new URL(source.url);
          if (!["http:", "https:"].includes(url.protocol)) continue;
          const link = node(
            "a",
            url.hostname +
              " · consulté le " +
              new Date(source.accessed_at).toLocaleDateString("fr-FR"),
          );
          link.href = url.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          article.append(link);
        } catch {
          /* Ignore malformed imported URLs. */
        }
      }
      $("hits").append(article);
    }
  } catch (error) {
    tell(error.message, true);
  }
});
$("note-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!$("selected").value) return;
  const saved = await action("/api/remember", {
    project_id: $("selected").value,
    title: $("note-title").value,
    text: $("note-text").value,
  });
  if (saved) {
    $("note-form").reset();
    tell("Décision conservée dans ce projet.");
  }
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
refresh();
setInterval(refresh, 5000);
