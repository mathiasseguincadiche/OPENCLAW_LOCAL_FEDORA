# Contribuer

## Règle principale

Une modification doit **préserver ou renforcer** les garanties existantes. Aucun changement ne peut être fusionné pour « faire passer » une qualification en abaissant silencieusement un seuil.

## Avant une PR

```bash
make install
make ci
```

## Exigences

- la plateforme reste Fedora-native ;
- la pile GPU nominale reste `xe` + Mesa/Vulkan ;
- pas de désactivation SELinux/firewalld ;
- pas de fallback cloud silencieux ;
- pas de promotion automatique de backend ; aucun noyau construit ou installé par le projet ;
- tout changement de performance doit conserver un benchmark comparable ;
- documentation et contrat exécutable doivent évoluer ensemble ;
- les scripts shell doivent passer ShellCheck ;
- les Actions GitHub doivent être pinées sur SHA complet.

## Changements matériels/performance

Une PR peut ajouter un candidat ou une optimisation Linux, mais elle ne peut pas le déclarer gagnant sans preuves matérielles observées sur la B580 cible.

## Contrôles natifs

`make ci` utilise des réponses de modèle simulées. Deux contrôles exécutent le vrai OpenClaw épinglé, sans modèle ni GPU, et tournent aussi en CI :

```bash
make native-schema   # la configuration générée est acceptée par OpenClaw
make native-budget   # consignes non tronquées, prompt réel dans le contexte quotidien
```

Ils demandent `openclaw` dans le `PATH` et `OPENCLAW_SCHEMA_PARALLEL_PATH` pointant vers le plugin Parallel épinglé. Toute modification des fichiers `agents/`, des outils autorisés ou du budget dans `config/core/openclaw_policy.yaml` doit les faire passer.
