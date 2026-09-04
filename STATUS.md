# État du projet

Dernière mise à jour : 2026-09-03.

Le dépôt est une **plateforme Fedora native dont le socle logiciel L0-L8 est désormais implémenté sur la branche L8**. Les états « implémenté logiciellement », « qualifié sur la machine cible », « READY_FOR_HUMAN_REVIEW » et « approuvé humainement pour préparer V1 » restent volontairement séparés.

## Complétude du code source

| Domaine | État logiciel |
|---|---|
| Fondation / contrats / CI | PASS |
| 8 agents + routage + workspaces | PASS |
| Moteur projet / Intake / Artifact Exchange | PASS |
| Installation complète Fedora | PASS logiciel — validation machine cible à produire |
| Provisionnement explicite des 3 modèles nominaux | PASS logiciel — validation machine cible à produire |
| Challenger Ministral hors routage | PASS logiciel — provisionnement et qualification réels à produire |
| Service OpenClaw systemd user | PASS logiciel — validation machine cible à produire |
| Health / repair / backup / restore / uninstall | PASS logiciel — validation machine cible à produire |
| Télémétrie locale | PASS logiciel |
| FinOps + limites | PASS logiciel |
| L2/L3 gates matériels | IMPLÉMENTÉS — preuves réelles à produire |
| L4 E2E OpenClaw | IMPLÉMENTÉ — preuve réelle à produire |
| L5 HARD-40M | IMPLÉMENTÉ — preuve réelle à produire |
| L6 comparaison runtimes/kernel/challenger | PASS logiciel — mesures réelles requises avant toute promotion |
| L7 Golden Projects + projet représentatif | PASS logiciel/CI — 5 Golden Projects + 1 projet représentatif déterministes |
| L8 release readiness | PASS logiciel — agrégation/recalcul fail-closed ; preuves réelles L2-L7 requises |
| L8 approbation humaine | IMPLÉMENTÉE mais NON EXÉCUTÉE — action humaine explicite requise après readiness réelle |

## Gates de qualification

| Gate | Objet | État des preuves |
|---|---|---|
| L0 | Fondation, contrats et CI | PASS |
| L1 | Cœur multi-agents Linux-native | PASS logiciel |
| L2 | Fedora 44 / hardware gate | PENDING — machine Fedora réelle requise |
| L3 | B580 `xe` + Mesa/Vulkan | PENDING — B580 réelle requise |
| L4 | OpenClaw + 8 agents + E2E | PENDING — E2E réel requis |
| L5 | Qualification HARD-40M | PENDING — flotte 9B/12B/14B à mesurer |
| L6 | Optimisation runtimes Linux + kernel 7.2.3 + challenger Ministral | PASS logiciel — mesures/recalculs réels requis |
| L7 | Golden Projects + projet représentatif | PASS logiciel/CI — moteur réel, sorties déterministes locales, gate humain préservé |
| L8 | Release Readiness / approbation humaine | LOGICIEL IMPLÉMENTÉ — runtime BLOQUÉ jusqu'aux preuves L2-L7 réelles puis approbation humaine explicite |

## Flotte nominale

- `qwen-max` → `qwen3.5:9b-q4_K_M` — 6,6 Go ;
- `gemma-deep` → `gemma3:12b-it-q4_K_M` — 8,1 Go ;
- `devstral-devops` → `qwen2.5-coder:14b-instruct-q4_K_M` — 9,0 Go.

Le contexte nominal est 8K. Le 16K reste un contexte de qualification, pas un réglage de production par défaut.

`ministral-3:14b-instruct-2512-q4_K_M` est un challenger obligatoire de `gemma-deep` uniquement. Il est provisionné par une commande L6 explicite, reste hors routage, ne compte pas dans la flotte requise et ne peut pas être promu automatiquement. Sa qualification couvre vision, qualité documentaire et tool-calling sur trois runs reproductibles.

## L8 — séparation readiness / approbation

Le framework L8 agrège les contrats logiciels et les preuves réelles L2-L7. Il recalcule les décisions L6 à partir de leurs snapshots avec les contrats courants au lieu de faire confiance à un verdict enregistré. Il vérifie notamment que les seuils HARD-40M correspondent encore au contrat courant, que les identités de modèles sont exactes et que les preuves restent sous `runtime/proofs`.

Un check L8 produit uniquement `BLOCKED` ou `READY_FOR_HUMAN_REVIEW` et écrit un manifeste SHA-256 des preuves. Même en état READY, `human_approval.status` reste `PENDING` et `v1_approved` reste `false`.

L'approbation est une commande séparée. Elle exige un rapport READY, une identité d'approbateur, `--acknowledge-v1`, une nouvelle collecte des preuves et le même hash d'ensemble de preuves. Elle écrit uniquement un record immuable `APPROVED_FOR_V1_PREPARATION` ; elle ne change pas le routage, ne promeut aucun candidat, ne passe aucun projet à `COMPLETE` et ne publie aucune release.

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
- Les trois alias `qwen-max`, `gemma-deep`, `devstral-devops` restent obligatoires et constituent exactement la flotte routée.
- Ministral reste hors flotte nominale et hors routage tant qu'une décision humaine distincte n'a pas explicitement choisi de remplacer Gemma.
- Le challenger Ministral ne peut jamais créer silencieusement un quatrième modèle opérationnel.
- Seul `qwen-max` reçoit les 3 probes Qwen thinking natifs.
- Le spécialiste DevOps est isolé sous la famille `qwen-coder` et ne reçoit pas ces probes.
- Les huit rôles agents restent exactement définis et `chef-operations` reste le défaut.
- `exec.mode=ask`, `elevated=false` et providers loopback-only restent obligatoires.
- Le moteur projet est fail-closed et `COMPLETE` requiert une approbation humaine explicite.
- L7 s'arrête à `PACKAGING` et ne peut jamais convertir automatiquement une preuve en approbation humaine L8.
- L8 readiness ne peut produire que `BLOCKED` ou `READY_FOR_HUMAN_REVIEW` ; jamais une approbation automatique.
- L8 recalcule les décisions L6 runtime, kernel et Gemma ↔ Ministral avec les contrats courants.
- L8 refuse une preuve HARD-40M dont les seuils ou la matrice diffèrent du contrat courant.
- L8 hash les preuves en SHA-256 et l'approbation refuse tout ensemble de preuves modifié après génération du rapport.
- L'approbation L8 nécessite une identité humaine et un acknowledgement explicite.
- Un record d'approbation L8 autorise uniquement la préparation V1 ; il ne modifie pas le runtime, le kernel, les modèles, `COMPLETE`, les tags ni les releases.
- Les entrées projet sont non fiables, inventoriées, hashées et revérifiées avant les changements de phase.
- Les bundles d'échange sont versionnés, immuables et revérifiés avant validation.
- Le package final est re-hashé avant `COMPLETE`.
- La racine runtime gérée possède `.openclaw-fedora-runtime` ; les suppressions destructives refusent une racine non marquée et `/`.
- L'installation et le provisionnement modèles restent dry-run/explicites.
- Le provisionnement nominal ne télécharge que les trois modèles routés ; Ministral utilise une commande challenger distincte.
- Les backups contiennent un manifeste SHA-256 et la restauration refuse l'écrasement.
- La désinstallation normale préserve projets, modèles et preuves.
- Télémétrie et FinOps sont locaux et hors Git.
- Les limites FinOps journalière, mensuelle et par projet sont appliquées sans override manuel.
- L2 exige Fedora/GNOME/Wayland, UEFI, ReBAR, SELinux et le hardware cible.
- L3 exige B580 + `xe` + render node + Mesa/Vulkan.
- L4 exige Gateway réel, 8 agents, tool-calling, réparation et stabilité 3/3.
- HARD-40M reste limité à 2400 secondes et 30 cas, préflight et évaluation inclus.
- Les runs longs utilisent `systemd-inhibit` pour bloquer la suspension.
- Les preuves runtime restent hors Git et les sorties brutes des modèles ne sont pas persistées par L5/L6.
- Les Golden Projects L7 exercent le vrai moteur projet et l'Artifact Exchange avec des sorties déterministes locales ; ils ne remplacent pas les preuves modèles/GPU de L4-L6.
- Aucun fallback cloud silencieux.
- SELinux reste Enforcing.
- Une V1 ne pourra être déclarée qu'après code complet, preuves matérielles/performance requises, readiness L8 réelle et approbation humaine explicite.
