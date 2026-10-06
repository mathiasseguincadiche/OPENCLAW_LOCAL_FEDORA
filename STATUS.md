# État du projet

Dernière mise à jour : 2026-10-06.

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
| 7 profils + routage + workspaces | PASS logiciel — mentor OPS et six spécialités sur Qwen unique |
| Politique outils `minimal` fail-closed | PASS logiciel |
| Moteur projet / Intake / Artifact Exchange | PASS logiciel |
| Installation complète Fedora 44 | IMPLÉMENTÉE — validation machine cible à produire |
| SELinux / firewalld / systemd-user / Podman / KVM | INTÉGRÉS au bootstrap/lifecycle |
| Provisionnement explicite de Qwen quotidien ; 3 modèles pour benchmark expérimental | IMPLÉMENTÉ — validation machine cible à produire |
| Challenger Granite hors routage | IMPLÉMENTÉ — qualification réelle à produire |
| OpenClaw **exactement 2026.9.8** + Parallel **exactement 2026.9.8** | VERROUILLÉS — contrats, convergence et contrôles exacts implémentés ; mises à jour automatiques interdites |
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

## Atelier local quotidien

OpenClaw/Parallel 2026.9.8 et Ollama 0.35.1 sont les nouveaux pins contractuels. Le schéma et la migration sont vérifiés avec le CLI OpenClaw réel dans une installation isolée. L'interface locale, la recherche SQLite FTS5, les décisions, les recherches datées et la pause/reprise sont implémentées ; aucun modèle supplémentaire n'est chargé. Les réponses JSON conformes ne nécessitent aucune réparation LLM.

Le tableau de bord a été exercé dans Chromium avec recherche et conservation d'une décision. Ces vérifications logicielles ne mettent pas à jour une installation Fedora existante et ne qualifient pas la B580. Voir [LOCAL_ASSISTANT.md](docs/LOCAL_ASSISTANT.md) et la migration dans [UPGRADE.md](docs/UPGRADE.md).

## Gates de qualification

| Gate | Objet | État des preuves |
|---|---|---|
| L0 | Fondation, contrats et CI | PASS logiciel |
| L1 | Cœur multi-agents Linux-native | PASS logiciel |
| L2 | Fedora 44 / hardware gate | PENDING — machine Fedora réelle requise |
| L3 | B580 `xe` + Mesa/Vulkan | PENDING — B580 réelle requise |
| L4 | OpenClaw 2026.9.8 exact + 6 agents + E2E | PENDING — E2E réel requis |
| L5 | Qualification HARD-40M | PENDING — flotte V2 à mesurer |
| L6 | Ollama/Vulkan, llama.cpp/Vulkan, kernel 7.2.3, Granite challenger | PENDING matériel — contrats logiciels PASS |
| L7 | Golden Projects + projet représentatif | PASS logiciel — replay installation finale requis avant L8 réel |
| L8 | Release Readiness / approbation humaine | BLOQUÉ jusqu'aux preuves L2-L7 réelles puis approbation explicite |

## Modèle quotidien et comparaisons expérimentales

Les sept rôles quotidiens utilisent uniquement `qwen3.5:9b-q4_K_M`, avec 8192 tokens de contexte, 1024 tokens de sortie et une génération à la fois. Les trois alias suivants sont conservés pour les campagnes de comparaison expérimentales :

- `qwen-max` → `qwen3.5:9b-q4_K_M` — Q4_K_M, multimodal ;
- `gemma-deep` → `gemma4:12b-it-q4_K_M` — Q4_K_M, multimodal ;
- `devstral-devops` → `hf.co/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:Q4_K_M` — Q4_K_M, text-only.

`devstral-devops` est un alias historique du benchmark DevOps. Le rôle quotidien `ingenieur-devops` utilise Qwen comme les six autres profils.

Le benchmark de référence reste à **8192 tokens**. Les comparaisons à 16K et les modèles supplémentaires ne modifient pas automatiquement le profil quotidien.

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
- **OpenClaw 2026.9.8 est l'unique version OpenClaw supportée par ce contrat.** Une version voisine, plus récente ou plus ancienne doit être refusée ; aucun canal `latest`, upgrade automatique ou convergence implicite vers une autre version n'est autorisé.
- Le plugin Parallel reste lui aussi verrouillé exactement en `2026.9.8`.
- Changer la version OpenClaw ou Parallel exige une modification contractuelle explicite, une branche dédiée et la requalification des gates affectés ; ce n'est pas une opération de maintenance courante.
- Le routage quotidien expose uniquement Qwen ; les trois alias de comparaison restent expérimentaux.
- Granite reste hors flotte nominale et hors routage tant qu'aucune décision humaine post-qualification ne change explicitement le contrat.
- Les probes Qwen thinking du protocole HARD-40M sont réservés aux benchmarks ; le quotidien utilise `think=false`.
- Les sept profils agents restent exactement définis et `chef-operations` reste le défaut.
- Le mentor coordonne l’aide OPS; les spécialités conservent leurs responsabilités et reçoivent des consignes pédagogiques compactes.
- La politique outils part de `minimal` ; les commandes et écritures natives des agents sont interdites, les résultats sont collectés par le worker.
- `intake/`, `sources/` et `context/exchange/` restent protégés et traçables.
- Le moteur projet est fail-closed et `COMPLETE` requiert une approbation humaine explicite.
- L8 readiness ne peut jamais approuver V1 automatiquement.
- Les preuves runtime restent hors Git et les sorties brutes modèles ne sont pas persistées par L5/L6. La comparaison mentor séparée conserve ses réponses pour la revue humaine, dans le rapport explicitement choisi.
- Aucun fallback LLM cloud silencieux.

## HARD-40M expérimental

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

## Mentor infrastructure/OPS et choix du modèle

Le mentor réutilise chef-operations, sans huitième agent. L’aide adaptative, les notes personnelles approuvées, la continuité du chat et les retours avant publication des brouillons sont implémentés. Le plugin interprète les rapports CI sans simuler leur exécution. La comparaison française Qwen/Gemma/Granite est préparée; ses tests automatisés utilisent des réponses simulées. Les mesures physiques, la qualité pédagogique du modèle réel et la promotion éventuelle de budgets plus grands restent à produire sur Fedora/B580. [Recherche et protocole](docs/MODEL_SELECTION_2026_10.md).
