/** Pure, no network/SDK project and chat contract shared with offline tests. */

export const AGENTS = Object.freeze([
  "chef-operations", "expert-recherche", "architecte-solutions",
  "ingenieur-devops", "ingenieur-securite", "redacteur-pedagogique",
  "auditeur-qualite",
]);
const PROJECT_ID = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;
const PROJECT_MARKER = /^📁 Projet : ([a-z0-9][a-z0-9-]{1,62}[a-z0-9])(?: · pont)?(?:\r?\n|$)/u;
const MAX_HISTORY_BYTES = 850_000;
const MAX_MESSAGES = 1000;

export function validateProject(raw) {
  if (typeof raw !== "string" || raw !== raw.trim()) {
    throw new Error("Projet LM Studio : utiliser un identifiant sans espaces.");
  }
  if (raw && !PROJECT_ID.test(raw)) {
    throw new Error("Projet LM Studio : identifiant invalide. Utilisez !projets pour le trouver.");
  }
  return raw;
}

export function validateAgent(role) {
  if (!AGENTS.includes(role)) {
    throw new Error("Agent LM Studio non reconnu : sélectionnez un des sept rôles.");
  }
  return role;
}

function getTextMessage(item) {
  if (!item || typeof item.getRole !== "function" || typeof item.getText !== "function") {
    throw new Error("Historique LM Studio incompatible avec le plugin.");
  }
  const role = item.getRole();
  if (!["user", "assistant", "system"].includes(role)) {
    throw new Error("Conversation avec outils ou rôle inconnu : ouvrir un chat ClawFedora dédié.");
  }
  const content = item.getText();
  if (typeof content !== "string" || content.includes("\u0000")) {
    throw new Error("Seuls les échanges textuels sont admis par le pont ClawFedora.");
  }
  // An assistant message may contain native tool calls without having role "tool".
  // Never erase those calls and silently forward its plain text as trusted history.
  if (role === "assistant" && typeof item.getToolCallRequests === "function") {
    const calls = item.getToolCallRequests();
    if (!Array.isArray(calls) || calls.length !== 0) {
      throw new Error("Historique avec appels d'outils LM Studio : nouveau chat ClawFedora dédié.");
    }
  }
  // LM Studio attachments are not an ingestion route for project documents.
  for (const method of ["getImages", "getFiles"]) {
    if (typeof item[method] === "function") {
      const attached = item[method]();
      if (Array.isArray(attached) && attached.length > 0) {
        throw new Error("Importer les pièces jointes dans l'Atelier Projets, pas dans ce chat.");
      }
    }
  }
  return { role, content };
}

export function bridgePayload(history, projectId, agentRole) {
  const id = validateProject(projectId);
  const role = validateAgent(agentRole);
  if (!Array.isArray(history) || history.length < 1 || history.length > MAX_MESSAGES) {
    throw new Error("Historique absent ou trop long : démarrer une nouvelle discussion.");
  }
  const messages = history.map(getTextMessage);
  if (messages.at(-1).role !== "user" || !messages.at(-1).content.trim()) {
    throw new Error("La dernière instruction doit être un message humain non vide.");
  }
  const seen = new Set();
  for (const message of messages) {
    if (message.role !== "assistant") continue;
    const marker = PROJECT_MARKER.exec(message.content);
    if (marker) seen.add(marker[1]);
  }
  if (seen.size > 1 || (seen.size > 0 && (!id || !seen.has(id)))) {
    throw new Error(
      "Historique associé à un autre projet : nouveau chat LM Studio requis. "
      + "Ne pas reclasser silencieusement une discussion.",
    );
  }
  const payload = {
    model: "openclaw/" + role,
    stream: false,
    messages,
  };
  if (id) payload.clawfedora_lmstudio_project = id;
  if (Buffer.byteLength(JSON.stringify(payload), "utf8") > MAX_HISTORY_BYTES) {
    throw new Error("Historique trop volumineux : archiver puis ouvrir un nouveau chat.");
  }
  return payload;
}

export function bridgeResponse(status, data) {
  if (
    typeof status !== "number" || !data || typeof data !== "object"
    || status < 200 || status >= 300
  ) {
    const reason = String(data?.error?.message ?? "service indisponible").slice(0, 300);
    throw new Error("ClawFedora a refusé la demande : " + reason);
  }
  const text = data?.choices?.[0]?.message?.content;
  if (typeof text !== "string" || !text || text.length > 100_000) {
    throw new Error("ClawFedora : réponse vide ou hors contrat.");
  }
  return text;
}
