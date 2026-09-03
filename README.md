# OPENCLAW_LOCAL_FEDORA

Plateforme **Linux-native, local-first et fail-closed** destinée à faire fonctionner l'équipe multi-agents OpenClaw sur Fedora 44 avec une Intel Arc B580, puis à mesurer objectivement si cette plateforme dépasse la baseline Windows.

> **État : 0.1.0 — migration candidate.** Ce dépôt ne revendique encore aucun gain de performance matériel et aucune qualification V1.

## Cible matérielle

- AMD Ryzen 7 7700 — 8 cœurs / 16 threads
- Intel Arc B580 — 12 Gio VRAM
- 48 Gio DDR5 minimum, 96 Gio cible d'évolution
- 2 × Crucial T705 PCIe 5.0 NVMe
- Fedora Linux 44 Workstation
- GNOME 50 / Wayland

## Choix d'architecture

```text
Fedora 44 / GNOME 50
        │
        ├── systemd user ── OpenClaw Gateway
        ├── Podman
        ├── KVM / libvirt
        │
        └── Intel Arc B580 / xe
                │
        ┌───────┴────────────┐
        │                    │
   Mesa Vulkan         Level Zero / SYCL
        │                    │
   ┌────┴─────┐              └── llama.cpp SYCL
   │          │
 Ollama   llama.cpp Vulkan
```

### Baseline vs candidats

| Élément | Baseline | Candidat |
|---|---|---|
| Kernel | Fedora officiel | Linux 7.2.3 upstream |
| GPU | Vulkan/Mesa | SYCL/Level Zero |
| Runtime LLM | Ollama Vulkan | llama.cpp Vulkan / SYCL |
| Promotion | manuelle | après preuves uniquement |

Le kernel 7.2.3 n'est **jamais** installé par le bootstrap initial et le kernel Fedora reste un rollback bootable obligatoire.

## Modèles conservés pour la parité

La flotte locale reste exactement composée de :

- `qwen-max` → `qwen3.8:27b`
- `gemma-deep` → `gemma4:26b`
- `devstral-devops` → `devstral-small-2:24b`

Aucun petit modèle de secours nominal et aucun fallback cloud silencieux.

## HARD-40M

Le contrat de qualification de référence est conservé pour permettre une comparaison Windows/Fedora crédible :

- 30 cas ;
- 24 cas 8K + 6 cas 16K ;
- 3 modèles obligatoires ;
- Qwen reasoning natif sur 3 probes dédiés ;
- 768 tokens max sur ces probes ;
- 210 s max par cas ;
- **2400 s / 40 min max pour le gate complet** ;
- aucun appel cloud pendant le benchmark.

L'implémentation complète du runner sera importée avec le cœur portable pendant le gate M1. Le contrat est déjà verrouillé par tests afin d'éviter sa dilution pendant la migration.

## Démarrage du socle

Le bootstrap est dry-run par défaut :

```bash
./menu.sh --action bootstrap
```

Pour appliquer sur une vraie Fedora 44 :

```bash
./menu.sh --action bootstrap --apply
```

Le script refuse une distribution autre que Fedora 44 et refuse de continuer si SELinux n'est pas Enforcing.

Après reconnexion de session pour appliquer les groupes GPU/libvirt :

```bash
./menu.sh --action validate
./menu.sh --action audit-strict
./menu.sh --action gpu
```

## Développement

```bash
make install
make ci
```

Les gates locaux couvrent :

- contrats YAML ;
- Ruff ;
- mypy strict ;
- pytest ;
- ShellCheck ;
- syntaxe Bash.

GitHub ajoute :

- Python 3.12 ;
- Python 3.13 ;
- conteneur **Fedora 44 réel** ;
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

## Migration depuis OPENCLAW_LOCAL

Le dépôt Windows reste **indépendant** et sert de baseline/rollback historique. La migration n'importe que le cœur portable.

À préserver : agents, orchestrateur, intake, Artifact Exchange, Golden Projects, FinOps, télémétrie, sécurité local-first, identité modèles, HARD-40M et readiness V1.

À remplacer : PowerShell, Registry, Task Scheduler, WSL2 nominal, drive letters et ACL Windows.

Voir :

- `docs/MIGRATION_PLAN.md`
- `docs/ARCHITECTURE.md`
- `docs/FEDORA_B580.md`
- `docs/KERNEL_POLICY.md`
- `docs/QUALIFICATION.md`
- `docs/OPENCLAW_SYSTEMD.md`
- `STATUS.md`

## Objectif de performance

La migration vise **≥ 10 % de gain agrégé** contre la baseline Windows sur la même machine, à modèles/quantifications/prompts/contextes identiques, avec :

- aucune régression fonctionnelle ;
- aucune régression sécurité ;
- aucune régression > 5 % sur un modèle individuel ;
- E2E OpenClaw PASS ;
- Golden Projects PASS ;
- validation humaine finale.

Si Fedora est meilleur opérationnellement mais n'atteint pas le gain chiffré, le projet le dira explicitement au lieu de fabriquer un verdict.

## Sécurité

- SELinux Enforcing obligatoire ;
- providers locaux loopback-only ;
- firewalld conservé ;
- secrets hors Git ;
- cloud désactivé par défaut ;
- aucune promotion automatique kernel/backend/V1.

## Licence

MIT.
