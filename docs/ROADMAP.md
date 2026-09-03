# Roadmap Linux-native

## Objectif

Construire OPENCLAW_LOCAL_FEDORA comme plateforme autonome Fedora 44 pour OpenClaw et Intel Arc B580, avec des gates reproductibles avant toute promotion de runtime, kernel ou V1.

## L0 — Fondation

- contrats YAML ;
- package Python ;
- Bash strict ;
- CI Python 3.12/3.13 ;
- job Fedora 44 ;
- Ruff, mypy, pytest, ShellCheck ;
- CodeQL et Dependency Review.

**Sortie :** tous les checks PASS.

## L1 — Cœur multi-agents

Implémenter nativement :

- les 8 agents ;
- Project Intake ;
- Project Orchestrator ;
- Artifact Exchange ;
- Golden Projects ;
- télémétrie ;
- FinOps ;
- identité des modèles ;
- readiness V1.

**Sortie :** contrats et tests fonctionnels PASS.

## L2 — Baseline matérielle Fedora

Sur la machine réelle :

- Fedora 44 ;
- GNOME 50 / Wayland ;
- kernel Fedora officiel ;
- SELinux Enforcing ;
- Ryzen 7 7700 ;
- 48 Gio RAM minimum ;
- B580 12 Gio ;
- ReBAR ;
- second T705 monté pour `/srv/openclaw-local`.

**Sortie :** `audit-strict` PASS.

## L3 — B580 Vulkan

Valider :

- module `xe` ;
- render node ;
- Mesa Vulkan ;
- `vulkaninfo` ;
- Ollama Vulkan ;
- llama.cpp Vulkan.

**Sortie :** GPU gate PASS et smokes runtime PASS.

## L4 — OpenClaw E2E

- Gateway géré par systemd user ;
- 8 agents ;
- routage local ;
- tool calling ;
- réparation après erreur ;
- stabilité ;
- aucun fallback cloud silencieux.

**Sortie :** E2E PASS.

## L5 — HARD-40M

- 30 cas ;
- 24 × 8K ;
- 6 × 16K ;
- trois modèles obligatoires ;
- 2400 s maximum.

**Sortie :** qualification PASS avec identité exacte des modèles et runtimes enregistrée.

## L6 — Optimisation Linux

Comparer à la baseline Fedora stock + Ollama Vulkan :

- llama.cpp Vulkan ;
- réglages runtime qualifiés ;
- kernel 7.2.3 contre kernel Fedora officiel.

Une variable change à la fois. Le kernel Fedora reste bootable.

**Sortie :** candidat gagnant reproductible sur trois runs, sans régression fonctionnelle ni sécurité.

## L7 — Validation fonctionnelle complète

- 5 Golden Projects ;
- projet représentatif ;
- preuves ;
- limites documentées ;
- télémétrie et FinOps validés.

**Sortie :** chaîne complète PASS.

## L8 — V1

Conditions cumulatives :

- L0 à L7 PASS ;
- preuves identifiées ;
- documentation cohérente ;
- aucun seuil abaissé pour forcer un PASS ;
- approbation humaine finale.

**Sortie :** autorisation explicite de préparer la V1.
