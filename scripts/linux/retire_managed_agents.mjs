// Use the public, pinned SDK's explicit roster deletion contract. No file cleanup.
import { realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const requireFromCli = createRequire(realpathSync(process.argv[2]));
const sdk = requireFromCli.resolve("openclaw/plugin-sdk/config-mutation");
const { mutateConfigFile } = await import(pathToFileURL(sdk).href);
const retired = ["main", "redacteur-technique", "ingenieur-release-forges"];
const active = ["chef-operations", "expert-recherche", "architecte-solutions",
  "ingenieur-devops", "ingenieur-securite", "auditeur-qualite"];
await mutateConfigFile({
  base: "source",
  writeOptions: {
    allowedAgentRosterRemovals: retired,
    persistCanonicalAgentRoster: true,
    unsetPaths: retired.map(id => ["agents", "entries", id]),
  },
  mutate(draft) {
    const entries = draft.agents?.entries;
    if (!entries || active.some(id => !entries[id])) {
      throw new Error("Daily roster incomplete; refusing retirement");
    }
    const unknown = Object.keys(entries).filter(id => !active.includes(id) && !retired.includes(id));
    if (unknown.length) throw new Error(`Unmanaged agents retained: ${unknown.join(", ")}`);
    for (const id of retired) delete entries[id];
    if (Array.isArray(draft.bindings)) {
      draft.bindings = draft.bindings.filter(binding => !retired.includes(binding.agentId));
    }
  },
});
console.log("MANAGED_AGENT_RETIREMENT=PASS files=preserved");
