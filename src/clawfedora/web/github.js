"use strict";

/* Only explicitly clicked, same-origin actions reach the loopback server.
 * Never accept or display a GitHub token in a browser field. */
const $ = (name) => document.getElementById(name);
const plans = { repo: null, policy: null, draft: null };
function message(text, error = false) {
  const target = $("github-status");
  target.textContent = text;
  target.classList.toggle("error", error);
}
function show(id, result) {
  $(id).textContent = JSON.stringify(result, null, 2);
}
async function api(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Action refusée");
  return data;
}
async function call(button, fn) {
  button.disabled = true;
  try {
    message("");
    return await fn();
  } catch (error) {
    message(error.message, true);
    return null;
  } finally {
    button.disabled = false;
  }
}
function repoValues() {
  return {
    name: $("repo-name").value.trim(),
    description: $("repo-desc").value.trim(),
  };
}
function policyValues() {
  return {
    repo: $("policy-repo").value.trim(),
    branch: $("policy-branch").value.trim(),
    kind: $("policy-kind").value,
  };
}
function draftValues() {
  return {
    project_id: $("draft-project").value,
    stage: $("draft-stage").value.trim(),
    repo: $("draft-repo").value.trim(),
    base_sha: $("draft-base-sha").value.trim(),
    branch: $("draft-branch").value.trim(),
    title: $("draft-title").value.trim(),
    body: $("draft-body").value.trim(),
  };
}
function invalidate(group) {
  plans[group] = null;
  $(group + "-apply-form").hidden = true;
}
for (const [name, form] of [
  ["repo", "repo-plan-form"], ["policy", "policy-plan-form"], ["draft", "draft-plan-form"],
]) {
  $(form).addEventListener("input", () => invalidate(name));
  $(form).addEventListener("change", () => invalidate(name));
}

$("repo-plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await call($("repo-plan-form").querySelector("button[type=submit]"), async () => {
    const values = repoValues();
    const result = await api("/api/github/create-plan", values);
    plans.repo = result;
    show("repo-result", result);
    $("repo-apply-form").hidden = false;
    $("repo-approve-name").value = "";
    $("repo-approve-manifest").value = "";
    $("repo-human").checked = false;
    message("Aperçu prêt. Aucune création distante.");
  });
});
$("repo-apply-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await call($("repo-apply-form").querySelector("button[type=submit]"), async () => {
    if (!plans.repo) throw new Error("Refaire l'aperçu après une modification.");
    const data = await api("/api/github/create-apply", {
      ...repoValues(), approve_name: $("repo-approve-name").value.trim(),
      approve_manifest: $("repo-approve-manifest").value.trim(),
      human_approved: $("repo-human").checked,
    });
    invalidate("repo");
    show("repo-result", data);
    message("Dépôt créé ; vérifier maintenant les protections sur GitHub.");
  });
});

$("audit-settings").addEventListener("click", async () => {
  await call($("audit-settings"), async () => {
    const result = await api("/api/github/settings-audit", { repo: policyValues().repo });
    show("policy-result", result);
    invalidate("policy");
    message("Réglages consultés sans écriture ; NOT_EVALUATED ne signifie pas désactivé.");
  });
});
$("policy-plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await call($("policy-plan-form").querySelector("button[type=submit]"), async () => {
    const result = await api("/api/github/policy-plan", policyValues());
    plans.policy = result;
    show("policy-result", result);
    $("policy-apply-form").hidden = false;
    $("policy-approve-repo").value = "";
    $("policy-approve-manifest").value = "";
    $("policy-human").checked = false;
    message("Plan de protection prêt. Aucune modification distante.");
  });
});
$("policy-apply-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await call($("policy-apply-form").querySelector("button[type=submit]"), async () => {
    if (!plans.policy) throw new Error("Refaire l'aperçu des protections.");
    const result = await api("/api/github/policy-apply", {
      ...policyValues(), approve_repo: $("policy-approve-repo").value.trim(),
      approve_manifest: $("policy-approve-manifest").value.trim(),
      human_approved: $("policy-human").checked,
    });
    invalidate("policy");
    show("policy-result", result);
    message("Demande de protection envoyée. Vérifier son application effective sur GitHub.");
  });
});
$("draft-audit").addEventListener("click", async () => {
  await call($("draft-audit"), async () => {
    const values = draftValues();
    const result = await api("/api/github/local-audit", {
      project_id: values.project_id, stage: values.stage,
    });
    show("draft-result", result);
    invalidate("draft");
    message("Audit documentaire local terminé ; aucune exécution de code.");
  });
});
$("draft-plan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await call($("draft-plan-form").querySelector("button[type=submit]"), async () => {
    const values = draftValues();
    const result = await api("/api/github/draft-plan", values);
    plans.draft = result;
    show("draft-result", result);
    $("draft-apply-form").hidden = false;
    $("draft-approve-repo").value = "";
    $("draft-approve-sha").value = "";
    $("draft-human").checked = false;
    message("PR brouillon : plan hors ligne prêt. Examiner tous les fichiers.");
  });
});
$("draft-apply-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await call($("draft-apply-form").querySelector("button[type=submit]"), async () => {
    if (!plans.draft) throw new Error("Refaire l'aperçu exact de la PR.");
    const result = await api("/api/github/draft-apply", {
      ...draftValues(), approve_repo: $("draft-approve-repo").value.trim(),
      approve_sha256: $("draft-approve-sha").value.trim(),
      human_approved: $("draft-human").checked,
    });
    invalidate("draft");
    show("draft-result", result);
    message("PR créée en brouillon. Lire le diff et contrôler la CI avant fusion.");
  });
});

async function projects() {
  try {
    const result = await fetch("/api/status");
    if (!result.ok) throw new Error("Projets indisponibles");
    const data = await result.json();
    $("draft-project").replaceChildren();
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "Choisir un projet terminé…";
    $("draft-project").append(empty);
    for (const project of data.projects || []) {
      const option = document.createElement("option");
      option.value = project.project_id;
      option.textContent = project.title + " — " + project.status;
      if (project.status !== "COMPLETE") option.disabled = true;
      $("draft-project").append(option);
    }
  } catch (error) {
    message(error.message, true);
  }
}
projects();
