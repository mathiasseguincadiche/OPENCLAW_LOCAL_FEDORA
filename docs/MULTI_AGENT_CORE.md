# Cœur multi-agents Linux-native

## Objectif

La couche L1 matérialise huit rôles OpenClaw sous Fedora sans dépendre d'un autre système d'exploitation. Les contrats sont versionnés dans Git ; les workspaces réels restent sous la racine runtime locale.

## Huit rôles

| Agent | Modèle nominal | Fallback local | Responsabilité |
|---|---|---|---|
| `chef-operations` | `qwen-max` | `gemma-deep` | cadrage, planification, coordination |
| `expert-recherche` | `qwen-max` | `gemma-deep` | recherche et vérification |
| `architecte-solutions` | `gemma-deep` | `qwen-max` | architecture et compromis |
| `ingenieur-devops` | `devstral-devops` | `qwen-max` | implémentation et automatisation |
| `ingenieur-securite` | `qwen-max` | `gemma-deep` | sécurité et risques |
| `ingenieur-release-forges` | `qwen-max` | `devstral-devops` | packaging et publication |
| `redacteur-technique` | `gemma-deep` | `qwen-max` | documentation technique |
| `auditeur-qualite` | `gemma-deep` | `qwen-max` | audit indépendant |

Le routage reste borné aux trois alias locaux qualifiables. Aucun modèle supplémentaire n'est introduit comme secours implicite.

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

Candidats Linux :

```bash
./menu.sh --action configure-openclaw --backend llama-cpp-vulkan --apply
./menu.sh --action configure-openclaw --backend llama-cpp-sycl --apply
```

Le configurateur applique une séquence fail-closed :

1. initialise la baseline OpenClaw si nécessaire ;
2. vérifie/active le plugin officiel requis par `parallel-free` ;
3. capture `openclaw config schema` ;
4. déploie les huit workspaces ;
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

Cette couche prépare L4 mais ne prouve pas encore le fonctionnement réel sur la machine Fedora/B580. Le passage de L4 exige une exécution matérielle des huit agents et du tool-calling, avec preuves enregistrées hors Git.
