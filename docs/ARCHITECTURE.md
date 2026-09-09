# Architecture cible

## Principe

OPENCLAW_LOCAL_FEDORA est une plateforme **Linux-native autonome**. La logique métier doit vivre dans le package Python et les services Linux ; Bash reste une couche d'entrée fine.

```text
Fedora 44 / GNOME 50 / Wayland
        │
        ├── systemd user ── OpenClaw Gateway
        │
        ├── Podman
        ├── KVM / libvirt
        │
        └── Intel Arc B580 / xe
                │
          Mesa / Vulkan
                │
        ┌───────┴───────┐
        │               │
     Ollama          llama.cpp
```

## Couche plateforme

- Fedora Linux 44 Workstation.
- GNOME 50, session Wayland.
- systemd user pour le cycle de vie du Gateway OpenClaw.
- SELinux Enforcing et firewalld conservés.
- `/srv/openclaw-local` comme racine de données lourdes lorsque le second NVMe est monté.
- `~/.local/share/openclaw-local` comme fallback utilisateur.
- Python dans un venv géré.
- Podman pour les conteneurs.
- KVM/libvirt pour la virtualisation.

## Couche GPU

La pile GPU supportée est **`xe` + Mesa/Vulkan**.

- `ollama-vulkan` : baseline initiale ;
- `llama-cpp-vulkan` : candidat runtime L6 utilisant la même pile Mesa/Vulkan.

Les comparaisons utilisent le même modèle, la même quantification, les mêmes prompts et les mêmes contextes. Aucun backend n'est promu automatiquement.

## Kernel

Deux lignes sont conservées :

1. kernel Fedora officiel : baseline supportée et rollback obligatoire ;
2. Linux 7.2.3 upstream : candidat performance.

Le kernel candidat ne peut être promu que s'il passe boot, GNOME/Wayland, B580/xe, Vulkan, OpenClaw, HARD-40M, E2E et stabilité, sans régression.

## Cœur fonctionnel

Le projet doit fournir nativement :

- 8 rôles agents ;
- Project Intake ;
- Project Orchestrator ;
- Artifact Exchange ;
- Golden Projects ;
- FinOps ;
- télémétrie ;
- verrou d'identité modèles ;
- sécurité local-first ;
- V1 Release Readiness Gate ;
- benchmark HARD-40M.

Chaque composant doit être implémenté ou adapté pour Fedora sans dépendance à un autre OS.

## État et preuves

Git ne contient que l'état attendu. Les données de runtime restent hors dépôt :

```text
/srv/openclaw-local/
├── runtime/
├── models/
├── workspaces/
├── projects/
├── proofs/
└── benchmarks/
```

Toute promotion de kernel ou backend doit pointer vers des preuves locales identifiées et reproductibles.
