# État du projet

Dernière mise à jour du socle : 2026-09-03.

Le dépôt est une **plateforme Fedora native en construction**, pas encore une plateforme matériellement qualifiée. Aucun gain de performance n'est revendiqué avant mesures reproductibles sur la machine cible.

| Gate | Objet | État |
|---|---|---|
| L0 | Fondation, contrats et CI | EN COURS |
| L1 | Cœur multi-agents Linux-native | À FAIRE |
| L2 | Fedora 44 kernel officiel : hardware gate | BLOQUÉ jusqu'à installation Fedora |
| L3 | B580 `xe` + Mesa/Vulkan | BLOQUÉ jusqu'à installation Fedora |
| L4 | OpenClaw + 8 agents + E2E | À FAIRE |
| L5 | Qualification HARD-40M | À FAIRE |
| L6 | Optimisation backend + kernel 7.2.3 | À FAIRE |
| L7 | Golden Projects + projet représentatif | À FAIRE |
| L8 | Approbation humaine V1 | À FAIRE |

## Invariants

- Fedora 44 + GNOME 50 + Wayland est la cible.
- Le kernel Fedora officiel reste toujours un rollback bootable.
- Linux 7.2.3 est un candidat de performance, jamais une promotion automatique.
- Intel Arc B580 utilise le driver kernel `xe`.
- Mesa/Vulkan est l'unique pile GPU de runtime du projet.
- Ollama Vulkan est la baseline runtime.
- llama.cpp Vulkan est le candidat runtime de performance.
- Les trois modèles Qwen/Gemma/Devstral restent obligatoires.
- HARD-40M reste limité à 2400 secondes et 30 cas.
- Aucun fallback cloud silencieux.
- SELinux reste Enforcing.
- Une V1 ne pourra être déclarée qu'après preuves matérielles et approbation humaine.
