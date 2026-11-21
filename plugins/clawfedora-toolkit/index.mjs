import { execFile } from "node:child_process";
import { join, isAbsolute } from "node:path";
const string = { type: "string", maxLength: 12000 };
const index = {type: "integer", minimum: 0, maximum: 7};
const labels = (maxItems) => ({type: "array", maxItems, items: {type: "string", maxLength: 60}});
const graph = {
  title: {type: "string", minLength: 1, maxLength: 60},
  nodes: {...labels(8), minItems: 1},
  boundaries: labels(8),
  edges: {type: "array", maxItems: 12, items: {type: "array", minItems: 2, maxItems: 2, items: index}},
  edge_labels: labels(12),
};
const definitions = [
  ["clawfedora_artifact", "Produire un fichier téléchargeable UTF-8 ou une source Markdown et ses exports PDF/DOCX/ODT/TXT. Retourner les références dans files; pour un export, inclure la source .md dans le même dossier. Aucun code exécuté.", {format:{type:"string",enum:["markdown","text","yaml","json","python","shell","hcl","ini","toml","xml","dockerfile","template"]},content:string,filename:{type:"string",maxLength:100,pattern:"^[A-Za-z0-9_.-]+$"},exports:{type:"array",maxItems:4,uniqueItems:true,items:{type:"string",enum:["pdf","docx","odt","txt"]}}}, ["format","content"]],
  ["clawfedora_search", "Chercher au maximum quatre passages texte dans le snapshot de ton rôle. Aucun embedding.", { query: string, scope: string }, ["query"]],
  ["clawfedora_outline", "Préparer une trame de document OPS; ne crée pas de fichier ni de preuve.", { kind: string, title: string }, ["kind"]],
  ["clawfedora_diagram", "Draw.io éditable et SVG de chaque vue. boundaries nomme la frontière de chaque nœud (vide si externe), edge_labels nomme chaque flux.", {...graph, views: {type: "array", maxItems: 7, items: {type: "object", properties: graph, additionalProperties: false, required: ["title", "nodes"]}}}, ["nodes"]],
  ["clawfedora_lab_request", "DevOps: préparer un critère de laboratoire à approuver.", {validator: {type: "string", enum: ["shellcheck","actionlint","ansible-lint","hadolint","terraform-fmt","terraform-validate","kubeconform"]}, files: {type: "array", minItems: 1, maxItems: 20, items: string}, expected: string}, ["validator","files","expected"]],
  ["clawfedora_doc_links", "Vérifier liens locaux et ancres de titres Markdown dans un snapshot. document est relatif au scope.", {scope: string, document: string, content: string}, ["scope","document","content"]],
  ["clawfedora_check", "DevOps/sécurité/audit: syntaxe JSON/YAML/Python et alertes OPS statiques; aucune exécution.", { format: { type: "string", enum: ["json", "yaml", "python", "text"] }, content: string }, ["format", "content"]],
];
definitions.push(
  ["clawfedora_ci_report", "Lire un rapport infrastructure importé, sans exécution ni certification de sa provenance; ne retourne aucun journal brut.", { format: { type: "string", enum: ["terraform-validate", "ci-checks", "trivy-image"] }, image_digest: {type:"string",pattern:"^sha256:[a-f0-9]{64}$"}, content: string }, ["format", "content"]],
  ["clawfedora_lint", "Contrôle métier réel et statique via ShellCheck, yamllint, PyMarkdown ou Gitleaks; résultat et preuve, sans exécuter la solution.", { format: { type: "string", enum: ["shell", "yaml", "markdown", "secrets"] }, content: string }, ["format", "content"]],
  ["clawfedora_tool_status", "Vérifier les outils métier disponibles pour ton rôle; ne lance aucun modèle.", {}, []],
);
const specialists = {
  clawfedora_diagram: ["architecte-solutions"],
  clawfedora_check: ["ingenieur-devops", "ingenieur-securite", "auditeur-qualite"],
  clawfedora_lint: ["ingenieur-devops", "ingenieur-securite", "redacteur-pedagogique", "auditeur-qualite"],
  clawfedora_lab_request: ["ingenieur-devops"],
  clawfedora_doc_links: ["redacteur-pedagogique", "auditeur-qualite"],
};
const roles = ["chef-operations", "expert-recherche", "architecte-solutions", "ingenieur-devops", "ingenieur-securite", "redacteur-pedagogique", "auditeur-qualite"];
const allowed = (name, role) => (specialists[name] ?? roles).includes(role);
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
