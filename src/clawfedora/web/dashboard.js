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
  chat: "Une discussion utilise le modèle local",
  proposed: "Proposition prête à vérifier et approuver",
  preparing: "Préparation et recherche documentaire",
  running: "Une spécialité travaille",
  paused: "Travail en pause",
  failed: "Une tâche demande votre attention",
  awaiting_validation: "Livrables prêts pour la validation",
  reviewing: "L’auditeur examine les livrables",
  reviewed: "Audit enregistré",
  interrupted: "Travail interrompu — reprise possible",
  awaiting_practice: "À vous de compléter et vérifier cette étape",
  awaiting_feedback: "Travail reçu : retour du spécialiste à demander",
  feedback: "Relecture ciblée de votre travail",
  feedback_ready: "Retour disponible : lire puis poursuivre",
  awaiting_next_step: "Étape soumise — préparez la suivante",
};
const eur = (n) => Number(n).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + " €";
function cloudLine(cloud) {
  if (!cloud) return "";
  const parts = [];
  if (cloud.state === "granted") parts.push("☁️ cloud autorisé");
  else if (cloud.state === "stale") parts.push("☁️ accord à renouveler (sources modifiées)");
  else if (cloud.state === "inactive") parts.push("☁️ accord en attente (cloud désactivé)");
  else parts.push("💻 local");
  if (cloud.last && cloud.last.model) parts.push("dernier modèle : " + cloud.last.model + " (" + (cloud.last.route === "cloud" ? "cloud" : "local") + ")");
  if (cloud.calls_cloud) parts.push("coût estimé : " + eur(cloud.cost_eur));
  return parts.join(" · ");
}
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
let refreshSequence = 0;
async function refresh() {
  if (document.hidden) return;
  try {
    const sequence = ++refreshSequence;
    const data = await api("/api/status");
    if (sequence !== refreshSequence) return;
    $("profile").textContent =
      data.profile === "gaming" ? "IA suspendue · GPU libéré" : "IA locale";
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
    $("discussions").hidden = !data.webui_installed;
    const worker = data.worker;
    $("activity").textContent =
      (phases[worker.phase] || "Aucun travail actif") +
      (worker.active && worker.task_id ? " · " + worker.task_id : "");
    const cloud = data.cloud || {};
    $("cloud-budget").textContent = !cloud.ready
      ? "Cloud : désactivé (tout reste en local)"
      : cloud.budget && cloud.budget.error
        ? "Cloud : budget illisible, appels refusés"
        : "Cloud : " + eur(cloud.budget.spent_eur) + " / " + eur(cloud.budget.cap_eur) + " ce mois-ci" +
          (cloud.budget.level === "warning" ? " · seuil d’alerte dépassé" : cloud.budget.level === "exhausted" ? " · plafond atteint" : "");
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
            (project.paused ? " · Pause demandée" : "") +
            (project.awaiting_practice ? " · À vous de pratiquer" : "") +
            (project.awaiting_feedback ? " · Retour à demander" : ""),
        ),
      );
      detail.append(node("p", cloudLine(project.cloud), "cloud-line"));
      if (project.cloud && project.cloud.pause)
        detail.append(node("p", "Pause cloud : " + project.cloud.pause.message, "error"));
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
          project.awaiting_feedback ? "Demander le retour" : project.paused ? "Reprendre" : "Préparer la prochaine étape",
        );
      pause.disabled =
        !["ASSIGNED", "IN_PROGRESS"].includes(project.status) || project.paused;
      resume.disabled =
        worker.active ||
        project.awaiting_practice ||
        data.profile === "gaming" ||
        !["ASSIGNED", "IN_PROGRESS"].includes(project.status);
      pause.addEventListener("click", () =>
        action("/api/pause", { project_id: project.project_id }),
      );
      resume.addEventListener("click", () =>
        action("/api/resume", { project_id: project.project_id }),
      );
      const manage = node("button", "Ouvrir le projet", "secondary");
      manage.addEventListener("click", () => loadProject(project.project_id));
      buttons.append(manage, pause, resume);
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

let openedProject = null;
let editorSequence = 0;
function field(form, label, value, multiline = false) {
  const wrap = node("label", label), input = node(multiline ? "textarea" : "input");
  input.value = value || "";
  input.maxLength = 12000;
  if (multiline) input.rows = 3;
  wrap.append(input); form.append(wrap);
  return input;
}
async function loadProject(id) {
  try {
    const sequence = ++editorSequence;
    const data = await api("/api/project?" + new URLSearchParams({ project: id }));
    if (sequence !== editorSequence) return;
    openedProject = id;
    $("project-editor").hidden = false;
    $("editor-heading").textContent = data.manifest.title;
    $("editor-state").textContent = states[data.manifest.status] || data.manifest.status;
    $("editor-actions").replaceChildren();
    const addAction = (label, path, extra = {}) => {
      const button = node("button", label);
      button.addEventListener("click", async () => {
        const sequence = editorSequence;
        button.disabled = true;
        const result = await action(path, { project_id: id, ...extra });
        if (result && sequence === editorSequence) { tell("Action reçue. Actualisez le dossier pour consulter le résultat."); await loadProject(id); }
        button.disabled = false;
      });
      $("editor-actions").append(button);
    };
    const reload = node("button", "Actualiser le dossier", "secondary");
    reload.addEventListener("click", () => loadProject(id));
    $("editor-actions").append(reload);
    if (["INTAKE_READY", "ANALYZED", "CLARIFICATION_REQUIRED"].includes(data.manifest.status))
      addAction("Proposer le cadrage avec le chef", "/api/propose-analysis");
    if (data.manifest.status === "ANALYZED") addAction("Proposer un plan court", "/api/propose-plan");
    if (data.manifest.status === "VALIDATING") addAction("Lancer la validation", "/api/audit", { kind: "validation" });
    if (data.manifest.status === "REVIEW") addAction("Lancer la relecture", "/api/audit", { kind: "review" });
    if (data.manifest.status === "PACKAGING") addAction("J’approuve la livraison finale", "/api/complete", { human_approved: true });
    renderCloud(id);
    $("artifacts").replaceChildren();
    for (const file of data.files) {
      const link = node("a", file.path + " · " + file.size + " octets");
      link.href = "/api/artifact?" + new URLSearchParams({ project: id, path: file.path });
      link.download = file.path.split("/").pop();
      const row = node("p"); row.append(link); $("artifacts").append(row);
    }
    $("clarifications").replaceChildren();
    for (const item of data.clarifications?.items || []) {
      const form = node("form"), answer = field(form, item.question, item.answer || "", true);
      if (item.status !== "OPEN") { answer.disabled = true; }
      else {
        const submit = node("button", "Enregistrer ma réponse"); submit.type = "submit"; form.append(submit);
        form.addEventListener("submit", async (event) => {
          event.preventDefault();
          const result = await action("/api/clarify", { project_id: id, id: item.id, answer: answer.value });
          if (result) await loadProject(id);
        });
      }
      $("clarifications").append(form);
    }
    $("proposal").replaceChildren();
    if (data.draft && !data.draft.approved) renderProposal(id, data.draft, data.learning);
    await renderMentor(id);
    if (sequence !== editorSequence) return;
    renderLearning(id, data);
    renderRevision(id, data);
  } catch (error) { tell(error.message, true); }
}
function renderProposal(id, draft, learning) {
  const form = node("form"), proposal = structuredClone(draft.proposal), inputs = {};
  form.append(node("h3", draft.kind === "analysis" ? "Cadrage proposé" : "Plan proposé"));
  const tasks = [];
  if (draft.kind === "analysis") {
    const labels = { summary: "Résumé", objectives: "Objectifs", constraints: "Contraintes", deliverables: "Livrables", ambiguities: "Ambiguïtés", missing_information: "Informations manquantes", risks: "Risques", decisions_required: "Décisions à prendre" };
    for (const [key, label] of Object.entries(labels)) {
      const value = key === "summary" ? proposal[key] : (proposal[key] || []).map(x => typeof x === "string" ? x : x.question || x.description || JSON.stringify(x)).join("\n");
      inputs[key] = field(form, label + (key === "summary" ? "" : " (une ligne par élément)"), value, true);
    }
    form.append(node("p", "Couverture déclarée par l’IA : vérifiez les sources et toute lecture partielle. Ne marquez pas un PDF comme lu sans lecture effective avec l’outil indiqué."));
    for (const doc of proposal.source_coverage || []) {
      const label = node("label", doc.document_id + " · " + doc.method), select = node("select");
      for (const status of ["READ", "PARTIAL", "UNREADABLE"]) { const option = node("option", status); option.value = status; select.append(option); }
      select.value = doc.status; select.addEventListener("change", () => { doc.status = select.value; });
      label.append(select); form.append(label);
    }
  } else {
    for (const task of proposal.tasks || []) {
      const group = node("fieldset"); group.append(node("legend", task.title));
      const values = {};
      for (const key of ["id", "title", "objective", "depends_on", "expected_outputs", "acceptance_criteria"]) {
        const labels = { id: "Identifiant de tâche", title: "Titre", objective: "Objectif", depends_on: "Dépendances (une par ligne)", expected_outputs: "Fichiers attendus (deliverables/identifiant/fichier.md)", acceptance_criteria: "Critères vérifiables (un par ligne)" };
        values[key] = field(group, labels[key], Array.isArray(task[key]) ? task[key].join("\n") : task[key], key !== "id" && key !== "title");
      }
      const label = node("label", "Spécialité"), role = node("select");
      for (const name of ["chef-operations", "expert-recherche", "architecte-solutions", "ingenieur-devops", "ingenieur-securite", "redacteur-pedagogique", "auditeur-qualite"]) { const option = node("option", name); option.value = name; role.append(option); }
      role.value = task.role; label.append(role); group.append(label); form.append(group);
      const support = node("select"), supportLabel = node("label", "Aide pour cette étape");
      for (const [value, text] of [["direct", "Explication et livrable complet"], ["guided", "Je choisis de pratiquer avec des indices"]]) { const option = node("option", text); option.value = value; support.append(option); }
      // AI suggestions never opt the human into mandatory practice.
      support.value = learning?.mode === "guided" ? "guided" : "direct";
      task.learning_mode = support.value;
      task.practice_opt_in = support.value === "guided";
      support.addEventListener("change", () => {
        task.learning_mode = support.value;
        task.practice_opt_in = support.value === "guided";
      });
      supportLabel.append(support); group.append(supportLabel);
      if (task.role === "redacteur-pedagogique") {
        const scope = node("select"), scopeLabel = node("label", "Portée de la rédaction");
        for (const [value, text] of [["final", "Synthèse finale : toutes les tâches techniques"], ["intermediate", "Document intermédiaire : ses seules sources"]]) { const option = node("option", text); option.value = value; scope.append(option); }
        scope.value = task.writing_scope || "final";
        task.writing_scope = scope.value;
        scope.addEventListener("change", () => { task.writing_scope = scope.value; });
        scopeLabel.append(scope); group.append(scopeLabel);
      }
      tasks.push({ task, values, role });
    }
  }
  const confirm = node("label"), checkbox = node("input"); checkbox.type = "checkbox"; checkbox.required = true;
  confirm.append(checkbox, document.createTextNode(" J’ai vérifié la proposition et les limites; j’approuve ce cadrage ou ce plan."));
  form.append(confirm);
  const submit = node("button", "Approuver et enregistrer"); submit.type = "submit"; form.append(submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!checkbox.checked) return;
    const lines = value => value.split("\n").map(s => s.trim()).filter(Boolean);
    for (const [key, input] of Object.entries(inputs)) proposal[key] = key === "summary" ? input.value : lines(input.value);
    for (const { task, values, role } of tasks) {
      for (const [key, input] of Object.entries(values)) task[key] = ["depends_on", "expected_outputs", "acceptance_criteria"].includes(key) ? lines(input.value) : input.value;
      task.role = role.value;
    }
    const result = await action("/api/approve", { project_id: id, kind: draft.kind, proposal, human_approved: true });
    if (result) await loadProject(id);
  });
  $("proposal").append(form);
}
$("create-form").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const uploads = [...$("project-files").files];
    if (uploads.length > 3 || uploads.reduce((n, f) => n + f.size, 0) > 8000000) throw new Error("Trois documents et 8 Mo maximum.");
    const files = [];
    for (const file of uploads) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let raw = "";
      for (let offset = 0; offset < bytes.length; offset += 8192) raw += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
      files.push({ name: file.name, content: btoa(raw) });
    }
    const result = await action("/api/create", { title: $("project-title").value, brief: $("project-brief").value, files, learning_mode: $("learning-mode").value, learning_goals: $("learning-goals").value.split("\n").map(s => s.trim()).filter(Boolean) });
    if (result) { $("create-form").reset(); await loadProject(result.project_id); tell("Projet créé; préparez son cadrage."); }
  } catch (error) { tell(error.message, true); }
});

async function renderMentor(id) {
  const area = $("mentor"); area.replaceChildren();
  const saved = (await api("/api/status")).mentor || {};
  if (openedProject !== id) return;
  const details = node("details"), form = node("form"), inputs = {};
  details.append(node("summary", "Mon accompagnement et la continuité du chat"));
  form.append(node("p", "Gardez un acquis, un blocage précis et une prochaine action. Ces notes facultatives aident à adapter les indices et à réutiliser une notion dans un autre exercice. Vous seul les enregistrez; aucun niveau n’est certifié automatiquement."));
  const examples = { background: "Ex. : je sais diagnostiquer DNS et les services Linux.", focus: "Ex. : rendre une configuration Ansible idempotente.", difficulties: "Ex. : je confonds check-mode et preuve d’une deuxième exécution.", evidence: "Ex. : deuxième exécution sans changement, logs conservés; observation déclarée.", next_step: "Ex. : prévoir puis vérifier l’effet d’une variable modifiée." };
  for (const [key, label] of Object.entries({ background: "Ce que je sais déjà", focus: "Ce que je travaille maintenant", difficulties: "Mes difficultés", evidence: "Ce que j’ai réalisé ou vérifié", next_step: "Ma prochaine étape" })) {
    const input = field(form, label, saved[key] || "", true); input.maxLength = 500; input.placeholder = examples[key]; inputs[key] = input;
  }
  const attach = node("input"), attachLabel = node("label"); attach.type = "checkbox"; attach.checked = saved.project_id === id;
  attachLabel.append(attach, document.createTextNode(" Relier le mentor à ce projet dans Open WebUI")); form.append(attachLabel);
  const button = node("button", "Enregistrer mes notes"); button.type = "submit"; form.append(button);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const data = Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.value]));
    if (await action("/api/mentor", { ...data, project_id: attach.checked ? id : "", human_approved: true })) tell("Notes du mentor enregistrées. Le chat reste sans écriture dans le projet.");
  });
  details.append(form); area.append(details);
}

function renderLearning(id, data) {
  const area = $("learning"); area.replaceChildren();
  area.append(node("h3", data.learning.mode === "direct" ? "Propositions directes" : "Apprendre avec une aide adaptée"));
  area.append(node("p", "Une soumission conserve votre travail et vos observations. Les audits restent requis; aucune compétence n’est déclarée acquise automatiquement."));
  for (const item of data.checkpoints || []) {
    if (item.feedback) area.append(node("h4", "Retour · " + item.task_id), node("p", item.feedback.feedback), node("p", "Prochaine action : " + item.feedback.next_action));
    if (item.status === "AWAITING_FEEDBACK") area.append(node("p", "Travail reçu. Demandez le retour; vous pouvez encore corriger puis resoumettre le brouillon. Les dépendants restent bloqués."));
    if (!["AWAITING_PRACTICE", "AWAITING_FEEDBACK"].includes(item.status)) continue;
    const form = node("form"), inputs = {};
    form.append(node("h4", item.task_id + " · " + item.role), node("pre", item.guidance));
    form.append(node("p", "Complétez l’amorce, puis indiquez ce que vous avez compris et vérifié. Aucun code n’est exécuté par ce formulaire."));
    for (const [path, content] of Object.entries(item.files)) {
      if (content.startsWith("@document-export:")) {
        const source = content.slice("@document-export:".length);
        form.append(node("h4", path), node("p", "Export produit depuis " + source + ". Modifiez la source Markdown ci-dessous; le fichier sera généré après relecture."));
        inputs[path] = {value: content};
        continue;
      }
      const graphical = path.endsWith(".drawio") || path.endsWith(".svg");
      const details = node("details");
      if (graphical) {
        form.append(node("h4", path), node("p", path.endsWith(".drawio")
          ? "Téléchargez l’ébauche, ouvrez-la dans Draw.io, modifiez-la et enregistrez-la. Remettez le fichier ici; sa sauvegarde habituelle est acceptée et convertie localement en XML lisible."
          : "Cet aperçu est séparé du schéma éditable. Après modification dans Draw.io, réexportez et remettez le SVG correspondant."));
        details.append(node("summary", "Voir le contenu du fichier")); form.append(details);
      }
      const input = field(graphical ? details : form, path, content, true); input.maxLength = 60000; input.rows = 8;
      inputs[path] = input;
      if (graphical) {
        const download = node("button", "Télécharger " + path.split("/").pop(), "secondary"); download.type = "button";
        download.addEventListener("click", () => {
          const url = URL.createObjectURL(new Blob([input.value], { type: "application/octet-stream" }));
          const link = node("a"); link.href = url; link.download = path.split("/").pop();
          document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
        const label = node("label", "Remettre le fichier modifié · " + path), upload = node("input"); upload.type = "file";
        upload.accept = path.endsWith(".drawio") ? ".drawio,.xml" : ".svg";
        upload.addEventListener("change", async () => {
          const file = upload.files[0]; if (!file) return;
          upload.setCustomValidity(""); upload.disabled = true;
          const submit = form.querySelector("button[type=submit]"); submit.disabled = true;
          try {
            if (file.size > 60000) throw new Error("Fichier limité à 60 000 octets.");
            const text = await file.text();
            if (!text.trim() || new TextEncoder().encode(text).length > 60000) throw new Error("Fichier vide ou trop volumineux.");
            input.value = text; tell("Fichier repris dans votre brouillon. Expliquez vos changements avant de soumettre.");
          } catch (error) { upload.setCustomValidity(error.message); tell(error.message, true); }
          finally { upload.disabled = false; submit.disabled = !!form.querySelector("input[type=file]:disabled"); }
        });
        label.append(upload); form.append(download, label);
      } else {
        const download = node("button", "Télécharger " + path.split("/").pop(), "secondary"); download.type = "button";
        download.addEventListener("click", () => {
          const url = URL.createObjectURL(new Blob([input.value], {type: "application/octet-stream"}));
          const link = node("a"); link.href = url; link.download = path.split("/").pop(); link.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
        form.append(download);
      }
    }
    const explanation = field(form, "Mon raisonnement et le travail effectué", "", true);
    explanation.required = true; explanation.maxLength = 2000;
    const observations = field(form, "Résultat observé, preuve ou limite (ex. pas encore exécuté)", "", true);
    observations.maxLength = 4000;
    const label = node("label"), approved = node("input"); approved.type = "checkbox"; approved.required = true;
    label.append(approved, document.createTextNode(" Je soumets mon travail; les observations sont exactes et les limites explicites."));
    form.append(label);
    const button = node("button", item.status === "AWAITING_FEEDBACK" ? "Modifier et resoumettre mon étape" : "Soumettre mon étape"); button.type = "submit"; form.append(button);
    form.addEventListener("submit", async event => {
      event.preventDefault(); if (!approved.checked) return;
      const files = Object.fromEntries(Object.entries(inputs).map(([path, input]) => [path, input.value]));
      const result = await action("/api/practice", { project_id: id, task_id: item.task_id, files, explanation: explanation.value, observations: observations.value, human_approved: true });
      if (result) { await loadProject(id); tell("Travail reçu. Reprenez pour demander le retour avant de poursuivre."); }
    });
    area.append(form);
  }
}

function renderRevision(id, data) {
  const area = $("revision"); area.replaceChildren();
  if (!["IN_PROGRESS", "VALIDATING", "REVIEW", "PACKAGING", "COMPLETE"].includes(data.manifest.status)) return;
  const details = node("details"), form = node("form"), select = node("select");
  details.append(node("summary", "Demander une modification cohérente du projet"));
  const label = node("label", "Contribution à reprendre");
  for (const task of data.tasks) { const option = node("option", task.task_id); option.value = task.task_id; select.append(option); }
  label.append(select); form.append(label);
  const reason = field(form, "Modification demandée et raison", "", true); reason.required = true; reason.maxLength = 2000;
  const preview = node("button", "Voir les tâches concernées", "secondary"); preview.type = "button";
  const affected = node("p"), confirmation = node("label"), approved = node("input"); approved.type = "checkbox"; approved.required = true;
  confirmation.append(approved, document.createTextNode(" J’approuve cette reprise. Les anciens livrables et audits seront archivés, puis les étapes concernées devront être reprises."));
  const submit = node("button", "Approuver la modification"); submit.type = "submit"; submit.disabled = true;
  const clear = () => { submit.disabled = true; approved.checked = false; affected.textContent = ""; };
  select.addEventListener("change", clear);
  preview.addEventListener("click", async () => {
    const result = await action("/api/revision-impact", { project_id: id, task_id: select.value });
    if (result) { affected.textContent = "À reprendre : " + result.affected_tasks.join(" → "); submit.disabled = false; }
  });
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (!approved.checked || submit.disabled) return;
    const result = await action("/api/revise", { project_id: id, task_id: select.value, reason: reason.value, human_approved: true });
    if (result) { await loadProject(id); tell("Reprise approuvée. Les contributions dépendantes et leurs audits doivent être renouvelés."); }
  });
  form.append(preview, affected, confirmation, submit); details.append(form); area.append(details);
}

async function renderCloud(id) {
  const box = $("cloud");
  box.replaceChildren();
  let info;
  try {
    info = await api("/api/cloud?" + new URLSearchParams({ project: id }));
  } catch (error) {
    box.append(node("p", "État cloud indisponible : " + error.message, "error"));
    return;
  }
  box.append(node("h3", "Cloud pour ce projet"), node("p", cloudLine(info)));
  const models = Object.entries(info.models || {});
  if (models.length)
    box.append(node("p", "Modèles utilisés : " + models.map(([name, n]) => name + " ×" + n).join(" · ")));
  if (info.pause) {
    box.append(node("p", "Le projet est en pause : " + info.pause.message, "error"));
    box.append(node("p", "Rien n’a été refait en local. Pour poursuivre en local, retirez l’accord cloud puis reprenez ; pour rester au cloud, corrigez la cause puis reprenez."));
  }
  const revoke = async () => {
    if (await action("/api/cloud-revoke", { project_id: id })) {
      tell("Accord cloud retiré : la suite de ce projet tourne en local.");
      await renderCloud(id);
    }
  };
  if (info.state === "none") {
    const details = node("details");
    details.append(node("summary", "Autoriser le cloud pour ce projet…"), node("p", info.consent_text));
    const check = document.createElement("input");
    check.type = "checkbox";
    check.id = "cloud-ack";
    const label = node("label", " J’ai lu ce texte et j’autorise le cloud pour ce projet uniquement");
    label.prepend(check);
    const approve = node("button", "Autoriser le cloud pour ce projet");
    approve.disabled = true;
    check.addEventListener("change", () => { approve.disabled = !check.checked; });
    approve.addEventListener("click", async () => {
      if (await action("/api/cloud-approve", { project_id: id, human_approved: true, acknowledged: true })) {
        tell("Accord enregistré : les prochaines étapes de ce projet iront au cloud.");
        await renderCloud(id);
      }
    });
    details.append(label, approve);
    box.append(details);
  } else {
    const button = node("button", "Retirer l’accord cloud (poursuivre en local)", "secondary");
    button.addEventListener("click", revoke);
    box.append(button);
  }
}
