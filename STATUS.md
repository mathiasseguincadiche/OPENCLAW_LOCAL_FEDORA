# État du projet

Dernière mise à jour : 2026-09-09.

Le dépôt est une **édition Fedora 44 Linux-native d'OPENCLAW_LOCAL**. Le socle logiciel L0-L8 est implémenté et la branche Architecture V2 Fedora passe la CI logicielle, y compris le contrat exécuté dans un conteneur `fedora:44`. Les états « code/CI cohérents », « qualifié sur la machine B580 », « READY_FOR_HUMAN_REVIEW » et « approuvé humainement pour préparer V1 » restent strictement séparés.

## Complétude du code source

| Domaine | État logiciel |
|---|---|
| Fondation / contrats / CI | PASS logiciel — CI GitHub Fedora V2 verte |
| Python 3.12 / 3.13 | PASS |
| Conteneur `fedora:44` | PASS contrats + tests logiciels |
| Ruff / mypy / pytest / couverture / ShellCheck | PASS |
| CodeQL / Dependency Review | soumis aux checks GitHub de la PR |
| Garde anti-drift Architecture V2 | PASS — anciens IDs modèles/OpenClaw interdits |
| 8 agents + routage + workspaces | PASS logiciel — mêmes missions et alias que Windows |
| Politique outils `minimal` fail-closed | PASS logiciel |
| Moteur projet / Intake / Artifact Exchange | PASS logiciel |
| Installation complète Fedora 44 | IMPLÉMENTÉE — validation machine cible à produire |
| SELinux / firewalld / systemd-user / Podman / KVM | INTÉGRÉS au bootstrap/lifecycle |
| Provisionnement explicite des 3 modèles nominaux | IMPLÉMENTÉ — validation machine cible à produire |
| Challenger Granite hors routage | IMPLÉMENTÉ — qualification réelle à produire |
| OpenClaw 2026.9.2 + Parallel 2026.9.2 | CONTRATS ET CONVERGENCE IMPLÉMENTÉS |
| Service OpenClaw systemd user | IMPLÉMENTÉ — validation machine cible à produire |
| Health / repair / backup / restore / uninstall | IMPLÉMENTÉ — validation machine cible à produire |
| Télémétrie locale | PASS logiciel |
| L2/L3 gates matériels | IMPLÉMENTÉS — preuves réelles à produire |
| L4 E2E OpenClaw | IMPLÉMENTÉ — preuve réelle à produire |
| L5 HARD-40M | IMPLÉMENTÉ — preuve réelle à produire |
| L6 runtime Vulkan/kernel/challenger DevOps | IMPLÉMENTÉ — mesures réelles requises avant toute promotion |
| L7 Golden Projects + projet représentatif | PASS logiciel — gate humain préservé |
| L8 release readiness | PASS framework logiciel — preuves réelles L2-L7 requises |
| L8 approbation humaine | IMPLÉMENTÉE mais NON EXÉCUTÉE |

## Gates de qualification

| Gate | Objet | État des preuves |
|---|---|---|
| L0 | Fondation, contrats et CI | PASS logiciel |
| L1 | Cœur multi-agents Linux-native | PASS logiciel |
| L2 | Fedora 44 / hardware gate | PENDING — machine Fedora réelle requise |
| L3 | B580 `xe` + Mesa/Vulkan | PENDING — B580 réelle requise |
| L4 | OpenClaw + 8 agents + E2E | PENDING — E2E réel requis |
| L5 | Qualification HARD-40M | PENDING — flotte V2 à mesurer |
| L6 | Ollama/Vulkan, llama.cpp/Vulkan, kernel 7.2.3, Granite challenger | PENDING matériel — contrats logiciels PASS |
| L7 | Golden Projects + projet représentatif | PASS logiciel — replay installation finale requis avant L8 réel |
| L8 | Release Readiness / approbation humaine | BLOQUÉ jusqu'aux preuves L2-L7 réelles puis approbation explicite |

## Flotte nominale Architecture V2

La flotte routée reste exactement à trois alias :

- `qwen-max` → `qwen3.5:9b-q4_K_M` — Q4_K_M, multimodal ;
- `gemma-deep` → `gemma4:12b-it-q4_K_M` — Q4_K_M, multimodal ;
- `devstral-devops` → `hf.co/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:Q4_K_M` — Q4_K_M, text-only.

`devstral-devops` reste l'alias historique du spécialiste DevOps. Sa mission, son rôle et son routage ne changent pas ; seule son identité modèle nominale est alignée sur Architecture V2.

Le benchmark nominal reste à **8192 tokens**. Les agents OpenClaw disposent d'un budget de contexte distinct prévu par la politique runtime pour absorber système, outils et orchestration. Cette différence ne vaut jamais promotion automatique du benchmark matériel.

`granite-devops` → `granite4.2:8b-q4_K_M` est le challenger du slot `devstral-devops`. Il reste hors routage et ne compte jamais comme quatrième modèle nominal. Son protocole L6 vérifie coding, tool-calling natif, réparation après retour d'outil, sécurité et performance sur runs répétés.

## Invariants Linux et agents

- Fedora 44 + GNOME 50 + Wayland est la cible.
- Intel Arc B580 utilise le driver kernel `xe` et Mesa/Vulkan comme pile GPU supportée.
- SELinux doit rester **Enforcing** ; un test ne peut pas être « réparé » par `setenforce 0`.
- firewalld est conservé et les providers/Gateway restent loopback-only.
- Les services OpenClaw applicatifs utilisent `systemd --user` lorsqu'ils ne nécessitent pas de privilèges système.
- Podman est le runtime conteneur Linux privilégié ; KVM/libvirt/OVMF fournit la virtualisation native.
- Le kernel Fedora officiel reste toujours un rollback bootable ; Linux 7.2.3 est un candidat L6 seulement.
- Ollama/Vulkan est la baseline runtime ; llama.cpp/Vulkan est l'unique candidat runtime L6.
- Les trois alias `qwen-max`, `gemma-deep`, `devstral-devops` constituent exactement la flotte routée.
- Granite reste hors flotte nominale et hors routage tant qu'aucune décision humaine post-qualification ne change explicitement le contrat.
- Seul `qwen-max` reçoit les 3 probes Qwen thinking natifs HARD-40M.
- Les huit rôles agents restent exactement définis et `chef-operations` reste le défaut.
- Les missions des agents ne sont pas redéfinies par l'édition Fedora ; les prompts ont été enrichis avec ingestion, provenance, Web/runtime evidence, Artifact Exchange et garanties Linux natives.
- La politique outils part de `minimal`, `exec.mode=ask`, `elevated=false` et réautorise uniquement ce qui est nécessaire au rôle.
- `intake/`, `sources/` et `context/exchange/` restent protégés et traçables.
- Le moteur projet est fail-closed et `COMPLETE` requiert une approbation humaine explicite.
- L8 readiness ne peut jamais approuver V1 automatiquement.
- Les preuves runtime restent hors Git et les sorties brutes modèles ne sont pas persistées par L5/L6.
- Aucun fallback LLM cloud silencieux.

## HARD-40M

Le contrat reste :

- 30 cas ;
- 24 cas 8K + 6 cas 16K ;
- 10 cas par modèle ;
- 3 probes Qwen natifs réservés à `qwen-max` ;
- 210 s max par cas ;
- 2400 s max pour le gate complet ;
- zéro appel LLM cloud ;
- aucun téléchargement implicite ;
- digest/quantification exacts ;
- préflights Fedora/B580 obligatoires ;
- `systemd-inhibit` pendant les runs longs.

Les scénarios Fedora couvrent systemd, SELinux, Kubernetes, Terraform, Ansible, rollback, architecture, Web freshness, tool intent/réparation et long contexte.

## L8 — séparation readiness / approbation

Le framework L8 agrège les contrats logiciels et les preuves réelles L2-L7. Un check L8 produit uniquement `BLOCKED` ou `READY_FOR_HUMAN_REVIEW` et écrit un manifeste SHA-256 des preuves.

Même en état READY, `human_approval.status` reste `PENDING` et `v1_approved` reste `false`. L'approbation exige une action humaine séparée et ne modifie ni le routage, ni le kernel, ni un backend, ni les modèles, ni `COMPLETE`, ni une release.

**État actuel : CI logicielle Fedora V2 validée ; aucune qualification matérielle B580, aucun nouveau verdict de performance et aucune approbation V1 ne sont déclarés par la CI.**
