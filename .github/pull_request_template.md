## Objectif

Décrire le problème réel et le résultat attendu.

## Type de changement

- [ ] cœur multi-agents Linux-native
- [ ] Fedora / Bash / systemd
- [ ] GPU / Mesa / Vulkan
- [ ] qualification / benchmark
- [ ] documentation / gouvernance

## Invariants

- [ ] aucun fallback cloud silencieux
- [ ] SELinux reste Enforcing
- [ ] aucun noyau construit ou installé par le projet
- [ ] aucune promotion automatique de backend
- [ ] aucun seuil abaissé pour forcer un PASS
- [ ] la pile nominale reste Fedora + xe + Mesa/Vulkan

## Preuves

- [ ] `make ci`
- [ ] CI GitHub verte
- [ ] preuve matérielle jointe si le changement revendique une performance
- [ ] documentation synchronisée avec le contrat exécutable
