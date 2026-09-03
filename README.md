# OPENCLAW_LOCAL_FEDORA

Plateforme Linux-native local-first pour orchestrer une équipe multi-agents OpenClaw sur Fedora 44, optimisée et qualifiée pour Intel Arc B580.

> État : bootstrap du dépôt. Aucun verdict de performance ou de qualification matérielle n'est encore revendiqué.

## Cible

- Fedora Linux 44 Workstation
- GNOME 50 / Wayland
- Intel Arc B580 12 GiB
- AMD Ryzen 7 7700
- Vulkan comme baseline GPU Linux
- SYCL/Level Zero comme candidat de performance à qualifier
- OpenClaw géré par systemd
- aucun fallback cloud implicite

Le kernel Fedora officiellement supporté reste la baseline de sûreté. Linux 7.2.3 est traité comme un candidat séparé qui devra battre la baseline sans régression avant toute promotion.
