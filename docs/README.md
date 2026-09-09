# Documentation OPENCLAW_LOCAL_FEDORA

Ce répertoire est la porte d'entrée de la documentation de l'édition **Fedora 44 Linux-native**.

La documentation est organisée par besoin opérateur. Les fichiers `config/*.yaml` restent la vérité machine pour les modèles, versions, routages, gates et politiques. Les documents expliquent comment utiliser ces contrats sans les redéfinir.

## Par où commencer ?

| Je veux… | Document |
|---|---|
| comprendre le produit en quelques minutes | [`../README.md`](../README.md) |
| installer la plateforme sur Fedora 44 | [`INSTALLATION.md`](INSTALLATION.md) |
| effectuer les premières vérifications et lancer un premier usage | [`GETTING_STARTED.md`](GETTING_STARTED.md) |
| administrer la plateforme au quotidien | [`OPERATIONS.md`](OPERATIONS.md) |
| diagnostiquer une panne ou un comportement anormal | [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) |
| mettre à jour OpenClaw, Ollama, un modèle, Mesa ou un kernel candidat | [`UPGRADE.md`](UPGRADE.md) |
| comprendre l'architecture Linux | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| comprendre les huit agents et leur routage | [`MULTI_AGENT_CORE.md`](MULTI_AGENT_CORE.md) |
| comprendre le moteur de projets | [`PROJECT_ENGINE.md`](PROJECT_ENGINE.md) |
| qualifier Fedora et l'Intel Arc B580 | [`QUALIFICATION.md`](QUALIFICATION.md) |
| comprendre la pile B580 / `xe` / Vulkan | [`FEDORA_B580.md`](FEDORA_B580.md) |
| comprendre la politique kernel | [`KERNEL_POLICY.md`](KERNEL_POLICY.md) |
| comprendre le Gateway `systemd --user` | [`OPENCLAW_SYSTEMD.md`](OPENCLAW_SYSTEMD.md) |
| comprendre le cycle de vie complet | [`LIFECYCLE.md`](LIFECYCLE.md) |
| consulter les étapes L0–L8 | [`ROADMAP.md`](ROADMAP.md) |
| connaître l'état réel du dépôt | [`../STATUS.md`](../STATUS.md) |
| contribuer au code | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| consulter la politique sécurité du dépôt | [`../SECURITY.md`](../SECURITY.md) |

## Documents de référence

### Utilisateur / opérateur

- **INSTALLATION.md** : prérequis, dry-run, installation, vérification et retour arrière.
- **GETTING_STARTED.md** : contrôles initiaux, commandes essentielles et premier parcours.
- **OPERATIONS.md** : runbook d'exploitation quotidienne.
- **TROUBLESHOOTING.md** : symptômes, diagnostic, correction, vérification et rollback.
- **UPGRADE.md** : upgrades contrôlés, une variable à la fois.

### Architecture / développement

- **ARCHITECTURE.md** : architecture cible Fedora native.
- **MULTI_AGENT_CORE.md** : huit rôles, workspaces et configuration OpenClaw.
- **PROJECT_ENGINE.md** : Intake, Orchestrator, Artifact Exchange et packaging.
- **LIFECYCLE.md** : contrat complet installation/maintenance/sauvegarde/désinstallation.

### Qualification / matériel

- **QUALIFICATION.md** : gates L2 à L8 et HARD-40M.
- **FEDORA_B580.md** : pile Intel Arc B580, `xe`, Mesa/Vulkan et SYCL candidat.
- **KERNEL_POLICY.md** : kernel Fedora nominal et candidat upstream.
- **ROADMAP.md** : progression fonctionnelle et de qualification.

## Vérités canoniques

Pour éviter les divergences documentaires :

1. **identités modèles** → `config/model_catalog.yaml` ;
2. **versions runtime** → `config/runtime_versions.yaml` ;
3. **routage agents** → `config/core/model_routing.yaml` ;
4. **outils agents** → `config/core/tool_policy.yaml` ;
5. **qualification** → `config/qualification_policy.yaml` ;
6. **optimisation L6** → `config/optimization_policy.yaml` ;
7. **release readiness** → `config/release_readiness.yaml`.

Une documentation ne doit jamais devenir une seconde configuration cachée.

## Invariant critique

Une CI verte démontre la cohérence logicielle du dépôt. Elle ne démontre pas la qualification réelle de Fedora 44, de l'Intel Arc B580, de Vulkan, des performances HARD-40M/L6 ni l'approbation V1. Ces preuves sont produites sur la machine cible et restent soumises aux gates prévus.
