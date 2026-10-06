# Cœur multi-agents Linux-native

> Profil quotidien : sept rôles, Qwen seul, 8K, worker séquentiel et outils en lecture. Voir [DAILY_PROFILE.md](DAILY_PROFILE.md). Les comparaisons de trois modèles et 16K sont expérimentales.

## Repères de progression

| Repère | Valeur |
|---|---|
| **Pour qui** | Toute personne qui suit le parcours et veut comprendre comment les sept rôles collaborent dans l’architecture. |
| **Position dans le parcours** | 6/14 |
| **Prérequis** | Avoir lu [`ARCHITECTURE.md`](ARCHITECTURE.md). |
| **Objectif** | Comprendre les sept agents, leur routage, leurs workspaces et la façon dont OpenClaw les configure sous Fedora. |
| **Résultat attendu** | Savoir distinguer identité, modèle nominal, workspace, outils et responsabilités de chaque rôle. |
| **Critère d’arrêt** | Si les notions de couche plateforme, runtime ou contrat restent floues, revenir à l’architecture avant de poursuivre. |
| **Continuer avec** | [`PROJECT_ENGINE.md`](PROJECT_ENGINE.md) |
| **Source de vérité** | `config/core/model_routing.yaml`, `config/core/tool_policy.yaml` et les contrats sous `agents/`. |

## Objectif

La couche L1 matérialise sept rôles OpenClaw sous Fedora sans dépendre d'un autre système d'exploitation. Les contrats sont versionnés dans Git ; les workspaces réels restent sous la racine runtime locale.

## Sept rôles sur un seul modèle

| Agent | Responsabilité |
|---|---|
| `chef-operations` | mentor infrastructure/OPS, aide adaptée, plan court et dépendances |
| `expert-recherche` | faits datés, sources et mécanismes |
| `architecte-solutions` | infrastructure, flux, schémas et décisions |
| `ingenieur-devops` | automatisation, CI/CD, exploitation et rollback |
| `ingenieur-securite` | menaces, droits, secrets et contrôles |
| `redacteur-pedagogique` | clarté et cohérence des contributions actuelles |
| `auditeur-qualite` | preuves, critères et qualité des explications |

Chaque rôle utilise `qwen-max` (`qwen3.5:9b-q4_K_M`) sans fallback vers un autre modèle. Les autres alias sont des expériences séparées. Le rédacteur ne remplace pas la pédagogie des spécialistes et n’est appelé que lorsqu’une synthèse est utile. Voir [le parcours guidé](LEARNING_WORKFLOW.md) et [les plugins métier](SPECIALIST_TOOLING.md).

## Workspaces

Les sources versionnées sont sous `agents/`. Le déploiement crée :

```text
/srv/openclaw-local/workspaces/<agent-id>/
├── AGENTS.md
├── IDENTITY.md
├── SOUL.md
├── CONTRACT.md
├── TOOLS.md
├── HEARTBEAT.md
├── PEDAGOGY.md
├── .openclaw-fedora-managed
└── projects/
```

Un répertoire non vide sans marqueur géré est refusé : le déploiement ne détruit jamais silencieusement un workspace étranger.

Commande directe :

```bash
./scripts/linux/03_deploy_agents.sh
```

Ou :

```bash
./menu.sh --action agents
```

## Configuration OpenClaw

Dry-run :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan
```

Application réelle :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan --apply
```

Candidat runtime Vulkan :

```bash
./menu.sh --action configure-openclaw --backend llama-cpp-vulkan --apply
```

Le configurateur applique une séquence fail-closed :

1. initialise la baseline OpenClaw si nécessaire ;
2. vérifie/active le plugin officiel requis par `parallel-free` ;
3. capture `openclaw config schema` ;
4. déploie les sept workspaces ;
5. génère un patch déterministe depuis les contrats ;
6. vérifie le backend local sélectionné ;
7. exécute `openclaw config patch --dry-run` ;
8. applique le patch ;
9. exécute `openclaw config validate --json` ;
10. vérifie l'inventaire des agents.

Le rendu peut également être inspecté sans toucher à OpenClaw :

```bash
clawfedora openclaw render \
  --runtime-root /srv/openclaw-local \
  --backend ollama-vulkan \
  --output /tmp/openclaw.patch.json
```

## Sécurité

- Gateway et providers locaux : loopback-only ;
- filesystem : workspace-only ;
- `exec.mode=ask` ;
- elevated désactivé ;
- entrées et échanges considérés non fiables ;
- aucune clé cloud dans le patch généré ;
- image/PDF restent sur Ollama tant qu'un backend alternatif multimodal n'est pas qualifié.

## Limite actuelle

Cette couche prépare L4 mais ne prouve pas encore le fonctionnement réel sur la machine Fedora/B580. Le passage de L4 exige une exécution matérielle des sept agents et du tool-calling, avec preuves enregistrées hors Git.
