import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { AGENTS, bridgePayload, bridgeResponse, validateProject } from "../src/contract.mjs";

const item = (role, content, extra = {}) => ({
  getRole: () => role,
  getText: () => content,
  ...extra,
});
const user = (text) => item("user", text);
const assistant = (text) => item("assistant", text);

test("LM Studio manifest and package entry point are real files", () => {
  const root = fileURLToPath(new URL("../", import.meta.url));
  const packageJson = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  const manifest = JSON.parse(readFileSync(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.equal(manifest.type, "plugin");
  assert.equal(manifest.runner, "node");
  assert.equal(manifest.name, "clawfedora-local");
  assert.equal(packageJson.private, true);
  assert.equal(packageJson.dependencies["@lmstudio/sdk"], "1.4.0");
  assert.ok(existsSync(root + packageJson.main));
});

test("canonical seven agents stay explicitly selectable", () => {
  assert.equal(AGENTS.length, 7);
  for (const role of AGENTS) {
    const payload = bridgePayload([user("Explique les flux")], "opsdesk", role);
    assert.equal(payload.model, "openclaw/" + role);
    assert.equal(payload.clawfedora_lmstudio_project, "opsdesk");
    assert.equal(payload.stream, false);
    assert.equal(payload.messages.length, 1);
  }
});

test("projectless chat does not acquire project permissions", () => {
  const p = bridgePayload([user("!projets")], "", "chef-operations");
  assert.equal(Object.hasOwn(p, "clawfedora_lmstudio_project"), false);
});

test("command and human approval remain last user messages", () => {
  const p = bridgePayload(
    [user("Bonjour"), assistant("📁 Projet : opsdesk · pont\n\nBienvenue"),
     user("approuver livraison ABCDEF")],
    "opsdesk", "chef-operations",
  );
  assert.deepEqual(p.messages.at(-1), {
    role: "user", content: "approuver livraison ABCDEF",
  });
  assert.equal(p.clawfedora_lmstudio_project, "opsdesk");
});

test("switching project inside the same chat is refused", () => {
  const history = [
    user("Question ancienne"),
    assistant("📁 Projet : ancien · pont\n\nAnciennes informations"),
    user("Le projet est maintenant opsdesk"),
  ];
  assert.throws(
    () => bridgePayload(history, "opsdesk", "chef-operations"),
    /nouveau chat LM Studio requis/,
  );
  assert.throws(
    () => bridgePayload(history, "", "chef-operations"),
    /nouveau chat LM Studio requis/,
  );
  assert.throws(
    () => bridgePayload(
      [assistant("📁 Projet : opsdesk\n\nA"), assistant("📁 Projet : ancien\n\nB"),
       user("Question")],
      "opsdesk", "chef-operations",
    ),
    /nouveau chat LM Studio requis/,
  );
});

test("model cannot choose an unknown role or project identifier", () => {
  assert.throws(
    () => bridgePayload([user("test")], "opsdesk", "superadmin"), /sept rôles/,
  );
  for (const id of ["../../tmp", "OpsDesk", " opsdesk ", "x", "a".repeat(70)]) {
    assert.throws(() => validateProject(id));
  }
});

test("require a human question and reject unsupported attachments", () => {
  assert.throws(
    () => bridgePayload([assistant("!lancer")], "opsdesk", AGENTS[0]),
    /message humain/,
  );
  assert.throws(
    () => bridgePayload([item("tool", "!lancer"), user("suite")], "opsdesk", AGENTS[0]),
    /rôle inconnu/,
  );
  assert.throws(
    () => bridgePayload(
      [item("user", "description", { getImages: () => ["private-image"] })],
      "opsdesk", AGENTS[0],
    ),
    /pièces jointes/,
  );
  assert.throws(
    () => bridgePayload([user(" ")], "opsdesk", AGENTS[0]),
    /non vide/,
  );
});

test("assistant tool calls cannot be hidden in plain-text LM Studio history", () => {
  const conversation = [
    assistant("J'ai préparé une action", {
      getToolCallRequests: () => [{ name: "execute", arguments: { command: "!lancer" } }],
    }),
    user("continue"),
  ];
  assert.throws(
    () => bridgePayload(conversation, "opsdesk", AGENTS[0]),
    /appels d'outils LM Studio/,
  );
  assert.throws(
    () => bridgePayload([
      assistant("Réponse", { getToolCallRequests: () => null }),
      user("suite"),
    ], "opsdesk", AGENTS[0]),
    /appels d'outils LM Studio/,
  );
  const normal = bridgePayload([
    assistant("📁 Projet : opsdesk · pont\\n\\nOK", { getToolCallRequests: () => [] }),
    user("!etat"),
  ], "opsdesk", AGENTS[0]);
  assert.equal(normal.messages.at(-1).content, "!etat");
});

test("no silent dropping of thousands of turns or large history", () => {
  assert.throws(
    () => bridgePayload(Array.from({ length: 1001 }, () => user("x")), "", AGENTS[0]),
    /trop long/,
  );
  assert.throws(
    () => bridgePayload([user("x".repeat(900_000))], "opsdesk", AGENTS[0]),
    /trop volumineux/,
  );
});

test("only validated bridge responses are displayed", () => {
  assert.equal(
    bridgeResponse(200, { choices: [{ message: { content: "📁 Projet : opsdesk\n\nOK" } }] }),
    "📁 Projet : opsdesk\n\nOK",
  );
  assert.throws(
    () => bridgeResponse(401, { error: { message: "jeton refusé" } }),
    /jeton refusé/,
  );
  assert.throws(
    () => bridgeResponse(200, { choices: [{ message: { content: "" } }] }),
    /réponse vide/,
  );
});
