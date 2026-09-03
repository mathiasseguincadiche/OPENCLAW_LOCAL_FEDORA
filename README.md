# OPENCLAW_LOCAL_FEDORA

Plateforme **Linux-native, local-first et fail-closed** destinée à faire fonctionner une équipe multi-agents OpenClaw sur Fedora 44 avec une Intel Arc B580.

> **État : 0.1.0 — code produit en cours de complétion avant qualification matérielle.** Aucun gain matériel ni verdict V1 n'est revendiqué avant mesures réelles sur la machine cible.

## Cible matérielle

- AMD Ryzen 7 7700 — 8 cœurs / 16 threads
- Intel Arc B580 — 12 Gio VRAM
- 48 Gio DDR5 minimum, 96 Gio cible d'évolution
- 2 × Crucial T705 PCIe 5.0 NVMe
- Fedora Linux 44 Workstation
- GNOME 50 / Wayland

## Architecture

```text
Fedora 44 / GNOME 50 / Wayland
        │
        ├── systemd user ── OpenClaw Gateway
        ├── Podman
        ├── KVM / libvirt
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

## Baseline et candidats

| Élément | Baseline | Candidat(s) |
|---|---|---|
| Kernel | Fedora officiel | Linux 7.2.3 upstream |
| GPU/runtime | Ollama Vulkan | llama.cpp Vulkan, llama.cpp SYCL/Level Zero |
| Promotion | manuelle | après preuves uniquement |

Le chemin nominal reste **Fedora + `xe` + Mesa/Vulkan + Ollama**. SYCL/Level Zero est un candidat Linux de performance : il est autorisé, mesuré séparément et ne doit jamais bloquer l'installation ou la qualification de la baseline.

Le kernel 7.2.3 n'est jamais installé par le bootstrap initial. Le kernel Fedora reste un rollback bootable obligatoire.

## Flotte de modèles

La flotte nominale est dimensionnée pour les **12 Gio de VRAM de la B580** :

- `qwen-max` → `qwen3.5:9b-q4_K_M` — 6,6 Go, vision/tools/thinking ;
- `gemma-deep` → `gemma3:12b-it-q4_K_M` — 8,1 Go, vision/documentaire ;
- `devstral-devops` → `qwen2.5-coder:14b-instruct-q4_K_M` — 9,0 Go, code/tools.

Les huit rôles agents et les trois alias restent inchangés. Seuls les modèles sous-jacents ont été redimensionnés.

Le contexte opérationnel nominal est **8192 tokens pour les trois modèles**. Le contexte 16384 est exercé uniquement par la qualification. Les fenêtres théoriques supérieures des modèles ne sont pas utilisées comme réglage nominal sur une carte 12 Gio.

`ministral-3:14b-instruct-2512-q4_K_M` est enregistré comme challenger de `gemma-deep` pour comparer vision/documentation à une option vision + tools/function-calling. Il ne compte pas dans les trois modèles requis et ne peut jamais être promu automatiquement.

Aucun petit modèle de secours nominal et aucun fallback cloud silencieux.

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

Le chemin complet prépare Fedora, crée la racine runtime gérée, installe/démarre Ollama si nécessaire, impose OpenClaw `2026.7.1-2`, provisionne explicitement les trois modèles, déploie les huit agents, applique la configuration locale et installe le Gateway comme service utilisateur systemd.

### Modèles

Le téléchargement des modèles est une opération volontaire, distincte de la qualification :

```bash
./menu.sh --action models
./menu.sh --action models --apply
```

Aucun benchmark ne télécharge implicitement un modèle absent.

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

## HARD-40M

Le contrat de qualification est :

- 30 cas ;
- 24 cas 8K + 6 cas 16K ;
- 12 scénarios couverts collectivement à 8K ;
- 10 cas par modèle ;
- 3 modèles obligatoires ;
- Qwen reasoning natif sur 3 probes dédiés de `qwen-max` uniquement ;
- le spécialiste `qwen-coder` n'hérite jamais de ces probes ;
- 768 tokens max sur ces probes ;
- 210 s max par cas ;
- **2400 s / 40 min max pour le gate complet** ;
- aucun appel cloud pendant le benchmark ;
- aucun téléchargement implicite de modèle ;
- endpoint Ollama loopback uniquement ;
- digest et quantification exacts enregistrés.

La qualification prend comme baseline **Fedora avec son kernel officiel et Ollama Vulkan**. Les candidats Linux sont comparés uniquement à cette baseline, à modèle, quantification, prompt et contexte identiques.

Le seuil HARD-40M reste volontairement à 6 tok/s tant que la B580 n'a pas fourni une nouvelle baseline réelle. L'objectif opérationnel de la flotte redimensionnée est de dépasser 10 tok/s de manière stable ; ce seuil ne sera relevé qu'après mesures reproductibles.

## Gates L2 à L5

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

## Développement

```bash
make install
make ci
```

Les gates locaux couvrent :

- contrats YAML ;
- contrats HARD-40M ;
- contrats de cycle de vie ;
- Ruff ;
- mypy strict ;
- pytest ;
- ShellCheck ;
- syntaxe Bash.

GitHub ajoute :

- Python 3.12 ;
- Python 3.13 ;
- conteneur Fedora 44 ;
- CodeQL ;
- Dependency Review.

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
- `L6` — optimisation Linux : llama.cpp Vulkan, SYCL/Level Zero et kernel 7.2.3 ;
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

## Sécurité

- SELinux Enforcing obligatoire ;
- providers locaux loopback-only ;
- firewalld conservé ;
- secrets hors Git ;
- cloud désactivé par défaut ;
- télémétrie locale sans prompts/réponses/documents/secrets ;
- FinOps avec limites journalière, mensuelle et par projet ;
- backup avant repair ;
- purge destructive explicitement opt-in ;
- aucune promotion automatique kernel/backend/modèle/V1.

## Licence

MIT.
