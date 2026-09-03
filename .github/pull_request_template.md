## Objectif

Décrire le problème réel et le résultat attendu.

## Type de changement

- [ ] cœur portable
- [ ] Fedora / Bash / systemd
- [ ] GPU / Vulkan / SYCL
- [ ] kernel
- [ ] qualification / benchmark
- [ ] documentation / gouvernance

## Invariants

- [ ] aucun fallback cloud silencieux
- [ ] SELinux reste Enforcing
- [ ] kernel Fedora rollback conservé
- [ ] aucune promotion automatique kernel/backend
- [ ] aucun seuil abaissé pour forcer un PASS
- [ ] aucune hypothèse Windows ajoutée au chemin nominal

## Preuves

- [ ] `make ci`
- [ ] CI GitHub verte
- [ ] preuve matérielle jointe si le changement revendique une performance
- [ ] documentation synchronisée avec le contrat exécutable
