# Plan de migration Windows → Fedora 44

## Objectif

Migrer OPENCLAW_LOCAL vers Fedora 44 sans perdre de fonctionnalité, tout en recherchant un gain de performance mesurable sur la même machine.

La migration suit des gates. Un gate en échec interdit le passage au suivant.

## M0 — Baseline Windows

Avant de modifier la machine :

- archiver le commit exact OPENCLAW_LOCAL ;
- archiver l'identité exacte des trois modèles ;
- conserver le résultat HARD-40M ;
- conserver E2E OpenClaw ;
- relever driver GPU, versions Ollama/llama.cpp, RAM, VRAM, kernel Windows et timings ;
- conserver les Golden Projects et le projet représentatif quand ils seront terminés.

**Sortie :** `WINDOWS_BASELINE` reproductible.

## M1 — Portabilité du cœur

- importer uniquement le code Python portable ;
- importer les 8 agents et contrats transversaux ;
- conserver Project Intake / Orchestrator / Artifact Exchange ;
- éliminer les dépendances Windows du cœur ;
- ajouter une abstraction plateforme si nécessaire.

**PASS :** tests unitaires identiques ou renforcés, aucune dépendance à PowerShell/Registry/WSL dans le cœur.

## M2 — Linux CI

- Python 3.12 et 3.13 ;
- Fedora 44 container contract ;
- Ruff, mypy, pytest ;
- Bash syntax + ShellCheck ;
- CodeQL ;
- Dependency Review.

**PASS :** toutes les protections vertes.

## M3 — Installation Fedora stock

Installer Fedora 44 Workstation et conserver son kernel officiel.

Valider :

- GNOME 50 ;
- Wayland ;
- SELinux Enforcing ;
- B580 visible ;
- module `xe` ;
- render node DRM ;
- ReBAR ;
- second T705 monté sur `/srv/openclaw-local` ;
- Podman ;
- KVM/libvirt.

**Interdit à ce stade :** kernel 7.2.3 custom, réglages agressifs, désactivation SELinux.

## M4 — GPU baseline

Installer/valider la pile Fedora :

- Mesa Vulkan ;
- Vulkan tools ;
- intel-compute-runtime ;
- Intel Level Zero ;
- OpenCL runtime ;
- outils DRM/IGT.

Exécuter :

```bash
./menu.sh --action audit-strict
./menu.sh --action gpu
```

**PASS :** B580 + xe + Vulkan + Level Zero fonctionnels.

## M5 — OpenClaw et agents

- installer la même version OpenClaw que Windows pour la comparaison de parité ;
- utiliser un Node supporté ;
- installer le Gateway en service systemd user ;
- migrer les 8 workspaces ;
- reconstruire le routing local ;
- exécuter les smokes agent, tool calling, réparation d'erreur et stabilité.

**PASS :** 8/8 agents, tool calling, repair, stabilité.

## M6 — Performance

### 1. Fedora kernel officiel

Comparer :

- Ollama Vulkan ;
- llama.cpp Vulkan ;
- llama.cpp SYCL/Level Zero.

### 2. Kernel 7.2.3

Installer en parallèle, sans supprimer le kernel Fedora.

Rejouer exactement les mêmes tests.

### Critère cible de migration

- gain agrégé visé : **≥ 10 %** contre Windows ;
- aucune régression fonctionnelle/sécurité ;
- aucune régression > 5 % sur un modèle individuel ;
- 3 runs de stabilité au minimum.

Le kernel 7.2.3 a son propre seuil plus strict de non-régression par rapport au kernel Fedora.

## M7 — Projets réels

- 5 Golden Projects ;
- ingestion multimodale ;
- projet représentatif complet ;
- packaging ;
- validation qualité/sécurité ;
- preuves réelles de télémétrie.

**PASS :** toutes les sorties attendues sont produites et validées.

## M8 — Promotion Fedora

Fedora devient plateforme nominale uniquement si M0→M7 sont PASS et après approbation humaine.

À ce moment seulement :

- backend gagnant inscrit comme nominal ;
- kernel gagnant inscrit comme nominal ;
- Windows rétrogradé en référence/rollback historique ;
- une release V1 peut être envisagée.

## Règle de rollback

À tout moment :

- le dépôt Windows reste indépendant ;
- les preuves Windows ne sont jamais écrasées ;
- le kernel Fedora officiel reste bootable ;
- aucune optimisation n'est conservée si elle n'est pas mesurée.
