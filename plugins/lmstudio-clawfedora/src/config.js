import { createConfigSchematics } from "@lmstudio/sdk";

// Values are the seven canonical IDs from config/core/agents.yaml.
// They are a user-operated per-chat setting, not instructions from the model.
export const configSchematics = createConfigSchematics()
  .field(
    "projectId",
    "string",
    {
      displayName: "Projet ClawFedora pour cette conversation",
      subtitle: "Identifiant exact ; !projets dans un chat sans projet pour les lister",
      placeholder: "opsdesk",
    },
    "",
  )
  .field(
    "agentRole",
    "select",
    {
      displayName: "Agent OpenClaw",
      subtitle: "L'agent et le projet peuvent être différents entre les conversations",
      options: [
        { value: "chef-operations", displayName: "Chef d'opérations" },
        { value: "expert-recherche", displayName: "Expert recherche" },
        { value: "architecte-solutions", displayName: "Architecte solutions" },
        { value: "ingenieur-devops", displayName: "Ingénieur DevOps" },
        { value: "ingenieur-securite", displayName: "Ingénieur sécurité" },
        { value: "redacteur-pedagogique", displayName: "Rédacteur pédagogique" },
        { value: "auditeur-qualite", displayName: "Auditeur qualité" },
      ],
    },
    "chef-operations",
  )
  .build();
