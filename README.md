# OPENCLAW_LOCAL_FEDORA

Plateforme **Fedora 44 Linux-native, LLM local-only et fail-closed** pour exécuter une équipe multi-agents OpenClaw sur une Intel Arc B580.

> **État : 0.1.0 — logiciel Fedora validé par CI, qualification matérielle en attente.** Une CI verte prouve la cohérence du dépôt ; elle ne constitue pas un PASS B580, Vulkan, HARD-40M/L6 ni une approbation V1.

## En bref

`OPENCLAW_LOCAL_FEDORA` est une édition Linux native : elle n'exécute pas la version Windows sous compatibilité. Installation, services, sécurité, conteneurs, virtualisation, GPU, exploitation et qualification reposent sur les primitives Fedora.

```text
Fedora 44 / GNOME 50 / Wayland
        │
        ├── systemd --user ── OpenClaw Gateway
        ├── SELinux Enforcing + firewalld
        ├── Podman
        ├── KVM / libvirt / OVMF
        │
        └── Intel Arc B580 / xe
                │
        ┌───────┴──────────────┐
        │                      │
   Mesa / Vulkan      Level Zero / SYCL
        │                      │
  Ollama / llama.cpp      llama.cpp SYCL
```

Le chemin nominal reste **Fedora + kernel officiel + `xe` + Mesa/Vulkan + Ollama**. Les backends llama.cpp et le kernel upstream défini par les contrats sont des candidats de qualification, jamais des promotions automatiques.

## Flotte Architecture V2

La flotte routée contient **exactement trois modèles locaux Q4_K_M** :

| Alias | Modèle nominal | Mission dominante |
|---|---|---|
| `qwen-max` | `qwen3.5:9b-q4_K_M` | orchestration, recherche, sécurité, release |
| `gemma-deep` | `gemma4:12b-it-q4_K_M` | architecture, documentation, audit |
| `devstral-devops` | `hf.co/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:Q4_K_M` | DevOps, code, réparation, tool-calling |

L'alias `devstral-devops` est conservé pour la compatibilité des contrats. `granite4.2:8b-q4_K_M` est un **challenger DevOps hors routage** : il ne compte jamais comme quatrième modèle nominal et ne peut pas être promu automatiquement.

Les identités exactes et les politiques de flotte sont canoniquement définies dans `config/model_catalog.yaml`.

## Huit agents

```text
chef-operations          -> qwen-max
expert-recherche         -> qwen-max
architecte-solutions     -> gemma-deep
ingenieur-devops         -> devstral-devops
ingenieur-securite       -> qwen-max
ingenieur-release-forges -> qwen-max
redacteur-technique      -> gemma-deep
auditeur-qualite         -> gemma-deep
```

Leurs missions restent spécialisées et leurs contrats détaillés vivent sous `agents/`. Voir [`docs/MULTI_AGENT_CORE.md`](docs/MULTI_AGENT_CORE.md).

## Installation rapide

Prérequis : Fedora 44 Workstation sur la machine cible, SELinux Enforcing et une session utilisateur normale.

```bash
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd OPENCLAW_LOCAL_FEDORA

./menu.sh --action validate
./menu.sh --action install
./menu.sh --action install --apply
./menu.sh --action health
```

Le premier `install` est un dry-run. L'application réelle doit être lancée depuis le compte Fedora de bureau, pas directement en root.

Guide complet : [`docs/INSTALLATION.md`](docs/INSTALLATION.md).

## Premiers contrôles

```bash
./menu.sh --action status
./menu.sh --action health
./menu.sh --action project-selftest
./menu.sh --action e2e-dry-run --backend ollama-vulkan
./menu.sh --action qualification-dry-run
```

Ces commandes permettent de valider progressivement le dépôt et le produit sans confondre dry-run, self-test et qualification matérielle.

Guide de prise en main : [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md).

## Exploitation quotidienne

Les commandes principales sont :

```bash
./menu.sh --action health
./menu.sh --action backup
./menu.sh --action repair
./menu.sh --action repair --apply
```

Pour le Gateway :

```bash
systemctl --user status openclaw-gateway.service
journalctl --user -u openclaw-gateway.service -n 100 --no-pager
openclaw gateway status
```

Le runbook opérateur complet est [`docs/OPERATIONS.md`](docs/OPERATIONS.md). Pour une panne, aller directement à [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

## Qualification

La qualification reste séparée du simple fonctionnement du produit :

```text
L2 Fedora/hardware
  ↓
L3 B580 / xe / Mesa-Vulkan
  ↓
L4 OpenClaw E2E / 8 agents / outils
  ↓
L5 HARD-40M
  ↓
L6 runtimes / kernel / challenger DevOps
  ↓
L7 Golden Projects
  ↓
L8 Release Readiness
  ↓
approbation humaine explicite
```

Le benchmark nominal utilise 8192 tokens ; les agents OpenClaw disposent de 16384 tokens pour leur contexte système/outils/orchestration. Le contexte agent 16K n'est pas une promotion automatique du benchmark.

Procédure complète : [`docs/QUALIFICATION.md`](docs/QUALIFICATION.md).

## Sécurité

Les invariants principaux sont :

- SELinux **Enforcing** ;
- firewalld actif ;
- Gateway et providers locaux en loopback ;
- LLM cloud non supporté dans le routage nominal ;
- outils agents en base `minimal` fail-closed ;
- `exec.mode=ask` et `elevated=false` ;
- `intake/`, `sources/` et `context/exchange/` protégés ;
- télémétrie locale sans prompts, réponses, documents ni secrets ;
- aucune promotion automatique de kernel, backend, modèle ou V1.

Voir [`SECURITY.md`](SECURITY.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) et les contrats sous `config/`.

## Données runtime

La racine préférée est :

```text
/srv/openclaw-local/
├── .openclaw-fedora-runtime
├── runtime/
├── models/
├── workspaces/
├── projects/
├── proofs/
├── benchmarks/
├── state/
└── backups/
```

Les poids modèles, workspaces runtime, preuves et données projet ne sont pas versionnés dans Git.

## Documentation

Le point d'entrée complet est [`docs/README.md`](docs/README.md).

| Besoin | Document |
|---|---|
| installation | [`docs/INSTALLATION.md`](docs/INSTALLATION.md) |
| premiers pas | [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) |
| exploitation / runbook | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| dépannage | [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) |
| upgrade | [`docs/UPGRADE.md`](docs/UPGRADE.md) |
| architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| agents | [`docs/MULTI_AGENT_CORE.md`](docs/MULTI_AGENT_CORE.md) |
| moteur projet | [`docs/PROJECT_ENGINE.md`](docs/PROJECT_ENGINE.md) |
| B580 | [`docs/FEDORA_B580.md`](docs/FEDORA_B580.md) |
| qualification | [`docs/QUALIFICATION.md`](docs/QUALIFICATION.md) |
| kernel | [`docs/KERNEL_POLICY.md`](docs/KERNEL_POLICY.md) |
| lifecycle | [`docs/LIFECYCLE.md`](docs/LIFECYCLE.md) |
| état réel | [`STATUS.md`](STATUS.md) |

## Développement

```bash
make install
make ci
```

GitHub valide notamment Python 3.12/3.13, Ruff, mypy, pytest avec couverture, ShellCheck, un conteneur `fedora:44`, CodeQL et Dependency Review.

## Source de vérité

La documentation explique le produit, mais les valeurs opérationnelles sont définies par les contrats :

- modèles → `config/model_catalog.yaml` ;
- versions → `config/runtime_versions.yaml` ;
- routage → `config/core/model_routing.yaml` ;
- outils → `config/core/tool_policy.yaml` ;
- qualification → `config/qualification_policy.yaml` ;
- L6 → `config/optimization_policy.yaml` ;
- L8 → `config/release_readiness.yaml`.

## Licence

MIT.
