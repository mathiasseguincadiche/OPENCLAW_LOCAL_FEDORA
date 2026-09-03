# OPENCLAW_LOCAL_FEDORA

Plateforme **Linux-native, local-first et fail-closed** destinée à faire fonctionner une équipe multi-agents OpenClaw sur Fedora 44 avec une Intel Arc B580.

> **État : 0.1.0 — qualification candidate.** Aucun gain matériel ni verdict V1 n'est revendiqué avant mesures réelles sur la machine cible.

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

La flotte locale est exactement composée de :

- `qwen-max` → `qwen3.8:27b`
- `gemma-deep` → `gemma4:26b`
- `devstral-devops` → `devstral-small-2:24b`

Aucun petit modèle de secours nominal et aucun fallback cloud silencieux.

## HARD-40M

Le contrat de qualification est :

- 30 cas ;
- 24 cas 8K + 6 cas 16K ;
- 12 scénarios couverts collectivement à 8K ;
- 10 cas par modèle ;
- 3 modèles obligatoires ;
- Qwen reasoning natif sur 3 probes dédiés ;
- 768 tokens max sur ces probes ;
- 210 s max par cas ;
- **2400 s / 40 min max pour le gate complet** ;
- aucun appel cloud pendant le benchmark ;
- aucun téléchargement implicite de modèle ;
- endpoint Ollama loopback uniquement ;
- digest et quantification exacts enregistrés.

La qualification prend comme baseline **Fedora avec son kernel officiel et Ollama Vulkan**. Les candidats Linux sont comparés uniquement à cette baseline, à modèle, quantification, prompt et contexte identiques.

## Démarrage du socle

Le bootstrap est dry-run par défaut :

```bash
./menu.sh --action bootstrap
```

Pour appliquer sur Fedora 44 :

```bash
./menu.sh --action bootstrap --apply
```

Le script refuse une distribution autre que Fedora 44 et refuse de continuer si SELinux n'est pas Enforcing.

Après reconnexion de session pour appliquer les groupes GPU/libvirt :

```bash
./menu.sh --action validate
./menu.sh --action hardware-l2
./menu.sh --action hardware-l3
```

## Gates L2 à L5

### Vérification sans modèle

```bash
./menu.sh --action qualification-dry-run
./menu.sh --action e2e-dry-run --backend ollama-vulkan
./menu.sh --action performance
```

### Profil de benchmark

Activation explicite du profil performance :

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
├── runtime/
├── models/
├── workspaces/
├── projects/
├── proofs/
└── benchmarks/
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

Voir :

- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/FEDORA_B580.md`
- `docs/KERNEL_POLICY.md`
- `docs/QUALIFICATION.md`
- `docs/OPENCLAW_SYSTEMD.md`
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
- aucune promotion automatique kernel/backend/V1.

## Licence

MIT.
