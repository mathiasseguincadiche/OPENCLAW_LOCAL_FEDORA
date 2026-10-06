import { execFile } from "node:child_process";
import { join, isAbsolute } from "node:path";
const string = { type: "string", maxLength: 12000 };
const definitions = [
  ["clawfedora_search", "Chercher au maximum quatre passages texte dans le snapshot de ton rôle. Aucun embedding.", { query: string, scope: string }, ["query"]],
  ["clawfedora_outline", "Préparer une trame de document OPS; ne crée pas de fichier ni de preuve.", { kind: string, title: string }, ["kind"]],
  ["clawfedora_diagram", "Architecte: proposer un schéma SVG inerte et Mermaid, huit nœuds maximum; retourner svg_reference comme contenu JSON de la sortie .svg attendue.", { nodes: { type: "array", items: { type: "string", maxLength: 60 }, minItems: 1, maxItems: 8 }, edges: { type: "array", maxItems: 12, items: { type: "array", items: { type: "integer", minimum: 0, maximum: 7 }, minItems: 2, maxItems: 2 } } }, ["nodes"]],
  ["clawfedora_check", "DevOps/sécurité/audit: syntaxe JSON/YAML/Python et alertes OPS statiques; aucune exécution.", { format: { type: "string", enum: ["json", "yaml", "python", "text"] }, content: string }, ["format", "content"]],
];
definitions.push(
  ["clawfedora_ci_report", "Lire un rapport infrastructure importé, sans exécution ni certification de sa provenance; ne retourne aucun journal brut.", { format: { type: "string", enum: ["terraform-validate", "ci-checks"] }, content: string }, ["format", "content"]],
  ["clawfedora_lint", "Contrôle métier réel et statique via ShellCheck, yamllint, PyMarkdown ou Gitleaks; résultat et preuve, sans exécuter la solution.", { format: { type: "string", enum: ["shell", "yaml", "markdown", "secrets"] }, content: string }, ["format", "content"]],
  ["clawfedora_tool_status", "Vérifier les outils métier disponibles pour ton rôle; ne lance aucun modèle.", {}, []],
);
const allowed = (name, role) => name === "clawfedora_diagram" ? role === "architecte-solutions" : name === "clawfedora_check" ? ["ingenieur-devops", "ingenieur-securite", "auditeur-qualite"].includes(role) : name === "clawfedora_lint" ? ["ingenieur-devops", "ingenieur-securite", "redacteur-pedagogique", "auditeur-qualite"].includes(role) : ["chef-operations", "expert-recherche", "architecte-solutions", "ingenieur-devops", "ingenieur-securite", "redacteur-pedagogique", "auditeur-qualite"].includes(role);
export default {
  id: "clawfedora-toolkit", name: "ClawFedora OPS Toolkit",
  register(api) {
    for (const [name, description, properties, required] of definitions) {
      api.registerTool((context) => {
        const role = context.agentId, workspace = context.workspaceDir;
        const runtime = process.env.OPENCLAW_LOCAL_FEDORA_ROOT;
        if (!workspace || !runtime || !isAbsolute(runtime) || !allowed(name, role)) return null;
        return {
          name, label: name, description,
          parameters: { type: "object", additionalProperties: false, properties, required },
          async execute(_id, params, signal) {
            const input = JSON.stringify(params);
            if (Buffer.byteLength(input) > 24000) throw new Error("Paramètres trop volumineux");
            // Fixed interpreter/module/arguments, never a shell or agent-selected executable.
            const result = await new Promise((resolve, reject) => {
              const child = execFile(join(runtime, "runtime/venv/bin/python"),
                ["-m", "clawfedora.agent_tools", role, workspace, name],
                { timeout: 10000, maxBuffer: 32000, signal, env: process.env },
                (error, stdout) => error ? reject(new Error(stdout || "Outil refusé")) : resolve(stdout));
              child.stdin.end(input);
            });
            return { content: [{ type: "text", text: result }], details: JSON.parse(result) };
          },
        };
      }, { name, optional: true });
    }
  },
};
