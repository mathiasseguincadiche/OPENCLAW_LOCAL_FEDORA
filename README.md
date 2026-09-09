# OPENCLAW_LOCAL_FEDORA

Plateforme **Linux-native, LLM local-only et fail-closed** destinée à faire fonctionner une équipe multi-agents OpenClaw sur Fedora 44 avec une Intel Arc B580.

> **État : 0.1.0 — édition Fedora en cours de qualification matérielle.** La conformité logicielle peut être démontrée par CI, mais aucun gain matériel ni verdict V1 n'est revendiqué avant mesures réelles sur la machine cible.

## Cible matérielle

- AMD Ryzen 7 7700 — 8 cœurs / 16 threads
- Intel Arc B580 — 12 Gio VRAM
- 48 Gio DDR5 minimum, 96 Gio cible d'évolution
- 2 × Crucial T705 PCIe 5.0 NVMe
- Fedora Linux 44 Workstation
- GNOME 50 / Wayland

## Architecture Linux native

```text
Fedora 44 / GNOME 50 / Wayland
        │
        ├── systemd --user ── OpenClaw Gateway
        ├── SELinux Enforcing
        ├── firewalld
        ├── Podman
        ├── KVM / libvirt / OVMF
        │
        └── Intel Arc B580 / xe
                │
        ┌───────┴──────────────┐
        │                      │
   Mesa / Vulkan      Level Zero / SYCL
        │                      │
  ┌─────┴─────┐          llama.cpp SYCL
  │           │
Ollama   llama.cpp Vulkan
```

Cette édition n'exécute pas un runtime Windows sous compatibilité. Installation, services, sécurité, conteneurs, virtualisation, GPU, qualification et lifecycle utilisent les primitives Fedora/Linux natives.

## Baseline et candidats

| Élément | Baseline | Candidat(s) |
|---|---|---|
| Kernel | Fedora officiel | Linux 7.2.3 upstream |
| GPU/runtime | Ollama Vulkan | llama.cpp Vulkan, llama.cpp SYCL/Level Zero |
| Promotion | manuelle | après preuves uniquement |

Le chemin nominal reste **Fedora + `xe` + Mesa/Vulkan + Ollama**. SYCL/Level Zero est un candidat Linux de performance : il est autorisé, mesuré séparément et ne doit jamais bloquer l'installation ou la qualification de la baseline.

Le kernel 7.2.3 n'est jamais installé par le bootstrap initial. Le kernel Fedora reste un rollback bootable obligatoire.

## Flotte de modèles Architecture V2

La flotte routée contient **exactement trois modèles locaux Q4_K_M** et respecte les mêmes alias et responsabilités que l'édition Windows de référence :

- `qwen-max` → `qwen3.5:9b-q4_K_M` — ~6,6 Gio, multimodal, orchestration/recherche/sécurité/release ;
- `gemma-deep` → `gemma4:12b-it-q4_K_M` — ~7,6 Gio, multimodal, architecture/documentation/audit ;
- `devstral-devops` → `hf.co/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:Q4_K_M` — ~8,24 Gio, text-only, DevOps/software engineering/tool-calling.

L'alias `devstral-devops` est conservé pour la compatibilité des contrats et des projets persistés. Il pointe désormais sur Ministral 3 14B Reasoning ; ce changement ne modifie ni la mission ni le routage du rôle `ingenieur-devops`.

Les huit rôles et leurs missions restent inchangés :

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

L'Auditeur peut utiliser `qwen-max` comme alternative indépendante lorsque le producteur utilise `gemma-deep`.

### Contexte

Deux contrats sont volontairement séparés :

- **8192 tokens** : contexte nominal du benchmark matériel et de HARD-40M ;
- **16384 tokens** : contexte nominal des agents OpenClaw pour absorber système, outils et réserve d'orchestration ;
- **>16K** : non promu sans qualification dédiée.

Le contexte OpenClaw 16K n'est pas une promotion automatique du benchmark B580.

### Challenger hors routage

`granite-devops` → `granite4.2:8b-q4_K_M` est un challenger de benchmark du slot `devstral-devops`. Il compare notamment coding, tool-calling natif, réparation après retour d'outil, comportement terminal et fit B580. Il **ne compte pas dans la flotte routée**, n'est jamais un fallback implicite et ne peut pas être promu automatiquement.

Aucun petit modèle de secours nominal et aucun fallback LLM cloud silencieux.

## OpenClaw et recherche Web

Le runtime initial de qualification est verrouillé sur :

- OpenClaw `2026.9.2` ;
- plugin officiel `@openclaw/parallel-plugin` `2026.9.2` ;
- recherche `parallel-free` ;
- Gateway loopback géré par `systemd --user`.

La recherche Web ne constitue pas un backend LLM cloud. Les sources récupérées sont traitées par les modèles locaux. Les faits externes actuels doivent être accompagnés d'une preuve de currentness ; les affirmations techniquement vérifiables doivent recevoir une preuve runtime récente lorsque le contrat l'exige.

## Cycle de vie du produit

Le dépôt doit pouvoir être installé et maintenu avant toute qualification matérielle.

### Installation complète

Dry-run :

```bash
./menu.sh --action install
```

Application :

```bash
./menu.sh --action install --apply
```

Le chemin complet vérifie Fedora 44, maintient SELinux Enforcing et firewalld, prépare la racine runtime gérée, installe/converge Ollama `0.32.14`, impose OpenClaw `2026.9.2`, provisionne explicitement les trois modèles nominaux, déploie les huit agents, applique la configuration locale et installe le Gateway comme service utilisateur systemd.

### Modèles

Le téléchargement des modèles est une opération volontaire, distincte de la qualification :

```bash
./menu.sh --action models
./menu.sh --action models --apply
```

Aucun benchmark ne télécharge implicitement un modèle absent. Le challenger Granite est également hors du provisionnement nominal.

### Santé, sauvegarde et réparation

```bash
./menu.sh --action health
./menu.sh --action backup
./menu.sh --action repair
./menu.sh --action repair --apply
```

Le health-check contrôle contrats, runtime géré, OpenClaw, Gateway, Ollama, inventaire des trois modèles et huit workspaces. La réparation crée un backup avant toute reconfiguration.

Les backups contiennent `state/`, `projects/`, `proofs/` et `workspaces/`, avec manifeste SHA-256. Les modèles et le virtualenv sont exclus car reproductibles.

### Désinstallation

```bash
./menu.sh --action uninstall
./menu.sh --action uninstall --apply
```

La désinstallation normale préserve projets, modèles et preuves. Une purge exige explicitement :

```bash
./menu.sh --action uninstall --apply --purge-data
```

Toute suppression destructive exige le marqueur `.openclaw-fedora-runtime` créé par le bootstrap et `/` est toujours refusé comme racine runtime.

Voir `docs/LIFECYCLE.md` pour le détail du cycle de vie, de la restauration, de la télémétrie et du FinOps.

## Sécurité des agents

La base d'outils OpenClaw est **`minimal` fail-closed**. Chaque rôle ne réautorise que les capacités nécessaires :

- Chef : orchestration/sessions, lecture et Web, sans écriture ni exec ;
- Recherche : lecture/Web/browser, sans écriture ni exec ;
- Architecte : writer borné à `context/architecture` et `diagrams` ;
- DevOps : édition/patch/exec dans son workspace ;
- Sécurité : lecture/scan/exec, sans modification directe des sources ;
- Release : outils d'implémentation et publication gouvernée ;
- Rédacteur : écriture documentaire, sans exec ;
- Auditeur : lecture/revue, sans correction silencieuse.

`intake/`, `sources/` et `context/exchange/` sont des entrées protégées. Les bundles d'Artifact Exchange sont versionnés, hashés et propagés uniquement selon les contrats de tâche.

## HARD-40M

Le contrat de qualification Fedora est :

- 30 cas ;
- 24 cas 8K + 6 cas 16K ;
- 12 scénarios Linux couverts collectivement à 8K ;
- 10 cas par modèle ;
- 3 modèles obligatoires ;
- Qwen reasoning natif sur 3 probes dédiés de `qwen-max` uniquement ;
- Gemma 4 et Ministral Reasoning suivent leur protocole nominal sans hériter artificiellement des probes Qwen ;
- 768 tokens max sur les probes Qwen natifs ;
- 210 s max par cas ;
- **2400 s / 40 min max pour le gate complet** ;
- aucun appel LLM cloud pendant le benchmark ;
- aucun téléchargement implicite de modèle ;
- endpoint Ollama loopback uniquement ;
- digest et quantification exacts enregistrés.

La suite reste réellement Linux : elle couvre notamment systemd, SELinux, Kubernetes, Terraform, Ansible, rollback, diagrammes, fraîcheur Web, tool intent/réparation et discipline long contexte.

La qualification prend comme baseline **Fedora avec son kernel officiel et Ollama Vulkan**. Les candidats Linux sont comparés uniquement à cette baseline avec des preuves comparables.

Le seuil HARD-40M reste volontairement à 6 tok/s tant que la B580 n'a pas fourni une nouvelle baseline réelle. Aucun seuil n'est relevé sur la base de CI ou d'une estimation.

## Gates L2 à L8

### Vérification sans modèle

```bash
./menu.sh --action qualification-dry-run
./menu.sh --action e2e-dry-run --backend ollama-vulkan
./menu.sh --action performance
```

### Profil de benchmark

```bash
./menu.sh --action performance --apply
```

### OpenClaw E2E

```bash
./menu.sh --action e2e --backend ollama-vulkan
```

Le gate L4 vérifie les 8 agents, le Gateway, le provider local, le tool-calling, la réparation après erreur outil et 3 runs de stabilité.

### Qualification réelle

```bash
./menu.sh --action qualification
```

Les runs L4/L5 sont exécutés sous `systemd-inhibit` pour bloquer la suspension pendant la preuve. Le chrono HARD-40M démarre avant les préflights L2/L3 ; le benchmark reçoit uniquement le budget restant avant la réserve d'évaluation.

### Optimisation L6

L6 compare sans promotion automatique :

- Ollama/Vulkan vs llama.cpp/Vulkan ;
- llama.cpp/SYCL/Level Zero comme candidat optionnel ;
- kernel Fedora vs kernel upstream 7.2.3 ;
- Ministral Reasoning vs Granite 4.2 8B pour le slot DevOps.

Une éventuelle promotion nécessite des preuves répétées et une décision humaine.

## Développement

```bash
make install
make ci
```

Les gates locaux couvrent :

- contrats YAML ;
- contrats agents/routage/outils ;
- contrats HARD-40M ;
- contrats de cycle de vie et L6/L8 ;
- Ruff ;
- mypy strict ;
- pytest ;
- ShellCheck ;
- syntaxe Bash.

GitHub ajoute :

- Python 3.12 ;
- Python 3.13 ;
- conteneur réel `fedora:44` ;
- CodeQL ;
- Dependency Review.

**Une CI verte démontre la cohérence logicielle, pas la qualification matérielle B580.**

## Données lourdes

Le dépôt Git ne stocke jamais modèles, workspaces, preuves ou résultats bruts.

Racine préférée sur le second NVMe :

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

Fallback utilisateur : `~/.local/share/openclaw-local`.

## Roadmap Linux

Le projet avance par gates :

- `L0` — fondation, contrats et CI ;
- `L1` — cœur multi-agents Linux-native ;
- `L2` — Fedora stock : hardware gate ;
- `L3` — B580 `xe` + Mesa/Vulkan ;
- `L4` — OpenClaw + 8 agents + E2E ;
- `L5` — qualification HARD-40M ;
- `L6` — optimisation Linux : llama.cpp Vulkan, SYCL/Level Zero, challenger DevOps et kernel 7.2.3 ;
- `L7` — Golden Projects + projet représentatif ;
- `L8` — approbation humaine V1.

Le cycle de vie installation/maintenance est transversal : il doit être complet avant les validations L2-L8.

Voir :

- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/FEDORA_B580.md`
- `docs/KERNEL_POLICY.md`
- `docs/QUALIFICATION.md`
- `docs/OPENCLAW_SYSTEMD.md`
- `docs/LIFECYCLE.md`
- `STATUS.md`

## Objectif de performance

La baseline est **Fedora stock + Ollama Vulkan**. L'objectif d'optimisation est **≥ 10 % de gain agrégé** lorsque c'est réaliste, avec :

- aucune régression fonctionnelle ;
- aucune régression sécurité ;
- aucune régression > 5 % sur un modèle individuel ;
- E2E OpenClaw PASS ;
- Golden Projects PASS ;
- validation humaine finale.

Le projet ne revendique aucun gain sans preuve reproductible.

## Sécurité Fedora

- SELinux Enforcing obligatoire ;
- providers et Gateway loopback-only ;
- firewalld conservé et actif ;
- services applicatifs privilégiés évités lorsque `systemd --user` suffit ;
- Podman privilégié pour les conteneurs ;
- secrets hors Git ;
- LLM cloud non supporté dans le routage nominal ;
- télémétrie locale sans prompts/réponses/documents/secrets ;
- backup avant repair ;
- purge destructive explicitement opt-in ;
- aucune promotion automatique kernel/backend/modèle/V1.

## Licence

MIT.
