# État du projet

Dernière mise à jour du socle : 2026-09-03.

Le dépôt est un **candidat de migration Fedora**, pas encore une plateforme qualifiée. Aucun gain de performance n'est revendiqué tant que la comparaison reproductible avec OPENCLAW_LOCAL/Windows n'est pas terminée.

| Gate | Objet | État |
|---|---|---|
| M0 | Baseline Windows complète et archivée | EN COURS hors de ce dépôt |
| M1 | Cœur portable + contrats Fedora | EN COURS |
| M2 | CI Linux/Fedora complète | EN COURS |
| M3 | Fedora 44 kernel officiel : hardware gate | BLOQUÉ jusqu'à installation Fedora |
| M4 | B580 Vulkan + Level Zero | BLOQUÉ jusqu'à installation Fedora |
| M5 | OpenClaw + 8 agents + E2E | À FAIRE |
| M6 | Comparaison backends + kernel 7.2.3 | À FAIRE |
| M7 | Golden Projects + projet représentatif | À FAIRE |
| M8 | Approbation humaine / Fedora nominal | À FAIRE |

## Invariants déjà décidés

- Fedora 44 + GNOME 50 + Wayland est la cible.
- Le kernel Fedora officiel reste toujours un rollback bootable.
- Linux 7.2.3 est un candidat de performance, jamais une promotion automatique.
- Intel Arc B580 utilise le driver kernel `xe`.
- Vulkan/Mesa est la baseline GPU Linux.
- llama.cpp SYCL/Level Zero est un candidat de performance.
- Les trois modèles Qwen/Gemma/Devstral restent obligatoires.
- HARD-40M reste limité à 2400 secondes et 30 cas.
- Aucun fallback cloud silencieux.
- SELinux reste Enforcing.
- Une V1 ne pourra être déclarée qu'après preuves matérielles et approbation humaine.
