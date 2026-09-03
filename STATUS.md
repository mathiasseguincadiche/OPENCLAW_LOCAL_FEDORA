# État du projet

Dernière mise à jour : 2026-09-03.

Le dépôt est une **plateforme Fedora native en construction**, pas encore une plateforme matériellement qualifiée. Aucun gain de performance n'est revendiqué avant mesures reproductibles sur la machine cible.

| Gate | Objet | État |
|---|---|---|
| L0 | Fondation, contrats et CI | PASS |
| L1 | Cœur multi-agents Linux-native | PASS logiciel — agents/runtime + moteur projet validés par CI Fedora 44 |
| L2 | Fedora 44 / hardware gate | PRÉPARÉ logiciel — preuve réelle requise sur la machine Fedora |
| L3 | B580 `xe` + Mesa/Vulkan | PRÉPARÉ logiciel — preuve réelle requise sur la B580 |
| L4 | OpenClaw + 8 agents + E2E | PRÉPARÉ logiciel — 8 smokes, outils, réparation et stabilité à exécuter réellement |
| L5 | Qualification HARD-40M | PRÉPARÉ logiciel — 30 cas et hard cap 2400 s à exécuter réellement |
| L6 | Optimisation runtimes Linux + kernel 7.2.3 | À FAIRE après baseline L5 PASS |
| L7 | Golden Projects + projet représentatif | À FAIRE |
| L8 | Approbation humaine V1 | À FAIRE |

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
- Les trois modèles Qwen/Gemma/Devstral restent obligatoires.
- Les huit rôles agents restent exactement définis et `chef-operations` reste le défaut.
- `exec.mode=ask`, `elevated=false` et providers loopback-only restent obligatoires.
- Le moteur projet est fail-closed et `COMPLETE` requiert une approbation humaine explicite.
- Les entrées projet sont non fiables, inventoriées, hashées et revérifiées avant les changements de phase.
- Les bundles d'échange sont versionnés, immuables et revérifiés avant validation.
- Le package final est re-hashé avant `COMPLETE`.
- L2 exige Fedora/GNOME/Wayland, UEFI, ReBAR, SELinux et le hardware cible.
- L3 exige B580 + `xe` + render node + Mesa/Vulkan.
- L4 exige Gateway réel, 8 agents, tool-calling, réparation et stabilité 3/3.
- HARD-40M reste limité à 2400 secondes et 30 cas, préflight et évaluation inclus.
- Les runs longs utilisent `systemd-inhibit` pour bloquer la suspension.
- Les preuves runtime restent hors Git et les sorties brutes des modèles ne sont pas persistées par L5.
- Aucun fallback cloud silencieux.
- SELinux reste Enforcing.
- Une V1 ne pourra être déclarée qu'après preuves matérielles et approbation humaine.
