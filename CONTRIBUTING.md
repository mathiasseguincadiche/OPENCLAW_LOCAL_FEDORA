# Contribuer

## Règle principale

Une modification doit **préserver ou renforcer** les garanties existantes. Aucun changement ne peut être fusionné pour « faire passer » une qualification en abaissant silencieusement un seuil.

## Avant une PR

```bash
make install
make ci
```

## Exigences

- pas de dépendance Windows dans le chemin Fedora nominal ;
- pas de désactivation SELinux/firewalld ;
- pas de fallback cloud silencieux ;
- pas de promotion automatique kernel/backend ;
- tout changement de performance doit conserver un benchmark comparable ;
- documentation et contrat exécutable doivent évoluer ensemble ;
- les scripts shell doivent passer ShellCheck ;
- les Actions GitHub doivent être pinées sur SHA complet.

## Changements matériels/performance

Une PR peut ajouter un candidat ou une optimisation, mais elle ne peut pas le déclarer gagnant sans preuves matérielles observées sur la B580 cible.
