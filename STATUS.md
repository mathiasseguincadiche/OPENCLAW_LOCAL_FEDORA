# État du projet

Dernière mise à jour : 2026-09-03.

Le dépôt est une **plateforme Fedora native dont le code source est en cours de complétion avant validation matérielle**. Les états « implémenté logiciellement » et « qualifié sur la machine cible » sont volontairement séparés.

## Complétude du code source

| Domaine | État logiciel |
|---|---|
| Fondation / contrats / CI | PASS |
| 8 agents + routage + workspaces | PASS |
| Moteur projet / Intake / Artifact Exchange | PASS |
| Installation complète Fedora | IMPLÉMENTÉ — validation CI en cours |
| Provisionnement explicite des modèles | IMPLÉMENTÉ — validation CI en cours |
| Service OpenClaw systemd user | IMPLÉMENTÉ — validation CI en cours |
| Health / repair / backup / restore / uninstall | IMPLÉMENTÉ — validation CI en cours |
| Télémétrie locale | IMPLÉMENTÉ — validation CI en cours |
| FinOps + limites | IMPLÉMENTÉ — validation CI en cours |
| L2/L3 gates matériels | IMPLÉMENTÉS — preuves réelles à produire |
| L4 E2E OpenClaw | IMPLÉMENTÉ — preuve réelle à produire |
| L5 HARD-40M | IMPLÉMENTÉ — preuve réelle à produire |
| L6 comparaison runtimes/kernel/challenger | À IMPLÉMENTER |
| L7 Golden Projects + projet représentatif | À IMPLÉMENTER |
| L8 release readiness / V1 | À IMPLÉMENTER |

## Gates de qualification

| Gate | Objet | État des preuves |
|---|---|---|
| L0 | Fondation, contrats et CI | PASS |
| L1 | Cœur multi-agents Linux-native | PASS logiciel |
| L2 | Fedora 44 / hardware gate | PENDING — machine Fedora réelle requise |
| L3 | B580 `xe` + Mesa/Vulkan | PENDING — B580 réelle requise |
| L4 | OpenClaw + 8 agents + E2E | PENDING — E2E réel requis |
| L5 | Qualification HARD-40M | PENDING — flotte 9B/12B/14B à mesurer |
| L6 | Optimisation runtimes Linux + kernel 7.2.3 | PENDING — code framework à finir puis mesures |
| L7 | Golden Projects + projet représentatif | PENDING — code à finir puis exécution réelle |
| L8 | Approbation humaine V1 | BLOQUÉ jusqu'aux preuves requises |

## Flotte nominale

- `qwen-max` → `qwen3.5:9b-q4_K_M` — 6,6 Go ;
- `gemma-deep` → `gemma3:12b-it-q4_K_M` — 8,1 Go ;
- `devstral-devops` → `qwen2.5-coder:14b-instruct-q4_K_M` — 9,0 Go.

Le contexte nominal est 8K. Le 16K reste un contexte de qualification, pas un réglage de production par défaut.

`ministral-3:14b-instruct-2512-q4_K_M` est un challenger de `gemma-deep` uniquement. Il ne compte pas dans la flotte requise et ne peut pas être promu automatiquement.

## Invariants

- Fedora 44 + GNOME 50 + Wayland est la cible.
- Le kernel Fedora officiel reste toujours un rollback bootable.
- Linux 7.2.3 est un candidat de performance, jamais une promotion automatique.
- Intel Arc B580 utilise le driver kernel `xe`.
- Mesa/Vulkan est la pile GPU nominale.
- Ollama Vulkan est la baseline runtime.
- llama.cpp Vulkan est un candidat direct.
- llama.cpp SYCL/Level Zero est un candidat Linux optionnel de performance.
- Un candidat optionnel ne bloque jamais la baseline.
- Les trois alias `qwen-max`, `gemma-deep`, `devstral-devops` restent obligatoires.
- Seul `qwen-max` reçoit les 3 probes Qwen thinking natifs.
- Le spécialiste DevOps est isolé sous la famille `qwen-coder` et ne reçoit pas ces probes.
- Les huit rôles agents restent exactement définis et `chef-operations` reste le défaut.
- `exec.mode=ask`, `elevated=false` et providers loopback-only restent obligatoires.
- Le moteur projet est fail-closed et `COMPLETE` requiert une approbation humaine explicite.
- Les entrées projet sont non fiables, inventoriées, hashées et revérifiées avant les changements de phase.
- Les bundles d'échange sont versionnés, immuables et revérifiés avant validation.
- Le package final est re-hashé avant `COMPLETE`.
- La racine runtime gérée possède `.openclaw-fedora-runtime` ; les suppressions destructives refusent une racine non marquée et `/`.
- L'installation et le provisionnement modèles restent dry-run/explicites.
- Les backups contiennent un manifeste SHA-256 et la restauration refuse l'écrasement.
- La désinstallation normale préserve projets, modèles et preuves.
- Télémétrie et FinOps sont locaux et hors Git.
- Les limites FinOps journalière, mensuelle et par projet sont appliquées sans override manuel.
- L2 exige Fedora/GNOME/Wayland, UEFI, ReBAR, SELinux et le hardware cible.
- L3 exige B580 + `xe` + render node + Mesa/Vulkan.
- L4 exige Gateway réel, 8 agents, tool-calling, réparation et stabilité 3/3.
- HARD-40M reste limité à 2400 secondes et 30 cas, préflight et évaluation inclus.
- Les runs longs utilisent `systemd-inhibit` pour bloquer la suspension.
- Les preuves runtime restent hors Git et les sorties brutes des modèles ne sont pas persistées par L5.
- Aucun fallback cloud silencieux.
- SELinux reste Enforcing.
- Une V1 ne pourra être déclarée qu'après code complet, preuves matérielles et approbation humaine.
