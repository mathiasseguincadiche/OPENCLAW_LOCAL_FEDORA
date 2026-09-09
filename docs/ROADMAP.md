# Roadmap Linux-native

## Objectif

Construire OPENCLAW_LOCAL_FEDORA comme plateforme autonome Fedora 44 pour OpenClaw et Intel Arc B580, avec des gates reproductibles avant toute promotion de runtime, kernel, modèle challenger ou V1.

## L0 — Fondation

- contrats YAML ;
- package Python ;
- Bash strict ;
- CI Python 3.12/3.13 ;
- job Fedora 44 ;
- Ruff, mypy, pytest, ShellCheck ;
- CodeQL et Dependency Review.

**Sortie :** tous les checks logiciels PASS.

## L1 — Cœur multi-agents

Implémenter nativement :

- les 8 agents et leurs missions inchangées ;
- Project Intake ;
- Project Orchestrator ;
- Artifact Exchange ;
- Golden Projects ;
- télémétrie ;
- FinOps ;
- identité et routage des modèles ;
- readiness V1.

La flotte routée reste exactement :

- `qwen-max` → `qwen3.5:9b-q4_K_M` ;
- `gemma-deep` → `gemma4:12b-it-q4_K_M` ;
- `devstral-devops` → `hf.co/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:Q4_K_M`.

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

**Sortie :** `audit-strict` PASS produit sur la machine cible.

## L3 — B580 Vulkan

Valider :

- module `xe` ;
- render node ;
- Mesa Vulkan ;
- `vulkaninfo` ;
- Ollama Vulkan.

`llama.cpp Vulkan` appartient à la comparaison L6 et ne conditionne pas la validité de la baseline L3.

**Sortie :** GPU gate PASS et smokes baseline runtime PASS sur B580 réelle.

## L4 — OpenClaw E2E

- OpenClaw `2026.9.2` ;
- Gateway géré par systemd user ;
- 8 agents ;
- routage local ;
- tool calling ;
- réparation après erreur ;
- stabilité ;
- aucun fallback cloud silencieux.

**Sortie :** E2E PASS sur l'installation Fedora cible.

## L5 — HARD-40M

- 30 cas ;
- 24 × 8K ;
- 6 × 16K ;
- trois modèles obligatoires ;
- 3 probes Qwen natifs réservés à `qwen-max` ;
- 2400 s maximum ;
- zéro appel cloud et zéro téléchargement implicite.

**Sortie :** qualification PASS avec identité exacte des modèles et runtimes enregistrée.

## L6 — Optimisation Linux

Comparer à la baseline Fedora officielle + Ollama Vulkan :

- llama.cpp Vulkan ;
- llama.cpp SYCL/Level Zero comme candidat optionnel ;
- réglages runtime qualifiés ;
- kernel 7.2.3 contre kernel Fedora officiel ;
- `granite4.2:8b-q4_K_M` contre le spécialiste nominal Ministral sur le slot `devstral-devops`.

La comparaison modèle mesure des capacités correspondant réellement à la mission DevOps : plan systemd utilisateur, tool-calling natif, réparation après feedback outil, sécurité et performance. Elle n'impose pas de test vision à un modèle text-only.

Une variable change à la fois. Les candidats optionnels ne bloquent jamais la baseline. Le kernel Fedora reste bootable.

La flotte opérationnelle reste **exactement composée de trois alias**. Granite est provisionné explicitement uniquement pour L6, reste hors routage, ne compte pas dans la flotte requise et ne peut jamais être promu automatiquement.

**Sortie :** décisions reproductibles sur trois runs, sans régression fonctionnelle ni sécurité. Les verdicts possibles restent `KEEP_BASELINE` ou `ELIGIBLE_FOR_HUMAN_PROMOTION` ; aucune décision ne modifie automatiquement la configuration.

## L7 — Validation fonctionnelle complète

- 5 Golden Projects ;
- projet représentatif ;
- preuves ;
- limites documentées ;
- télémétrie et FinOps validés.

L7 s'arrête à `PACKAGING` et préserve le gate humain final.

**Sortie :** chaîne complète PASS côté moteur projet, sans `COMPLETE` automatique.

## L8 — V1

### L8.A — Release Readiness

Conditions cumulatives :

- L0 à L7 PASS ;
- preuves L2 à L7 présentes sous la racine runtime gérée ;
- preuves identifiées et hashées en SHA-256 ;
- décisions L6 runtime, kernel et Ministral ↔ Granite recalculables avec les contrats courants ;
- documentation cohérente ;
- aucun seuil abaissé pour forcer un PASS ;
- aucun fallback cloud ni promotion automatique.

Le gate produit uniquement :

- `BLOCKED` ; ou
- `READY_FOR_HUMAN_REVIEW`.

**Sortie :** `RELEASE_READINESS_REPORT.json`. Ce rapport n'approuve jamais V1.

### L8.B — Approbation humaine explicite

L'approbation est une action séparée qui exige :

- un rapport `READY_FOR_HUMAN_REVIEW` ;
- une identité d'approbateur explicite ;
- `--acknowledge-v1` ;
- une nouvelle validation de toutes les preuves courantes ;
- le même hash d'ensemble de preuves que le rapport soumis.

Elle écrit un enregistrement immuable `APPROVED_FOR_V1_PREPARATION` sous `proofs/l8/approvals/`.

Cette action ne :

- modifie pas le routage ;
- ne promeut ni runtime, ni kernel, ni modèle ;
- ne passe aucun projet à `COMPLETE` ;
- ne crée ni tag ni release GitHub ;
- ne publie rien automatiquement.

**Sortie :** autorisation humaine explicite de **préparer** la V1. La création/publication effective de la release reste une opération distincte.

## Principe de preuve

Un PASS de CI démontre la cohérence logicielle du dépôt. Il ne vaut jamais preuve matérielle B580, Vulkan, performance ou V1. Ces états ne peuvent être promus qu'à partir des preuves runtime prévues par les gates correspondants.
