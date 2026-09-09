# Documentation OPENCLAW_LOCAL_FEDORA

Ce répertoire est la porte d'entrée de la documentation de l'édition **Fedora 44 Linux-native**.

La règle est simple : **une seule documentation, un seul parcours, compréhensible par tout le monde**. Aucune partie n'est réservée à un « débutant », un « opérateur » ou un « expert ». Une personne qui ouvre le projet sans connaître son contexte doit pouvoir suivre l'ordre indiqué ci-dessous et acquérir progressivement les notions nécessaires jusqu'à comprendre l'architecture, l'exploitation, le matériel, les changements contrôlés et la qualification DevOps du projet.

Les fichiers `config/*.yaml` restent la vérité machine pour les modèles, versions, routages, gates et politiques. La documentation explique ces contrats sans les redéfinir.

## Parcours unique

Commencer au README racine, puis suivre simplement cet ordre :

```text
README racine
   ↓
1. GETTING_STARTED.md       comprendre les états et les commandes de base
   ↓
2. INSTALLATION.md          installer sans contourner les garde-fous
   ↓
3. OPERATIONS.md            exploiter, observer, sauvegarder et réparer
   ↓
4. TROUBLESHOOTING.md       apprendre le diagnostic couche par couche
   ↓
5. ARCHITECTURE.md          comprendre comment les composants s'assemblent
   ↓
6. MULTI_AGENT_CORE.md      comprendre les 8 agents, modèles et outils
   ↓
7. PROJECT_ENGINE.md        comprendre le cycle d'un projet et les artefacts
   ↓
8. OPENCLAW_SYSTEMD.md      comprendre le Gateway comme service Linux
   ↓
9. LIFECYCLE.md             comprendre le cycle de vie complet du produit
   ↓
10. FEDORA_B580.md          comprendre B580 → xe → Mesa/Vulkan → runtime
   ↓
11. KERNEL_POLICY.md        comprendre baseline, candidat et rollback kernel
   ↓
12. UPGRADE.md              apprendre à changer une seule variable à la fois
   ↓
13. QUALIFICATION.md        comprendre et exécuter les preuves L2 à L8
   ↓
14. ROADMAP.md              relire l'ensemble du projet comme une progression
   ↓
STATUS.md                   vérifier l'état réellement atteint aujourd'hui
```

La technicité augmente progressivement, mais le vocabulaire et les prérequis sont introduits au fil du parcours. Un lecteur n'est jamais envoyé vers une « zone expert » séparée : il continue simplement la même documentation.

## Contrat de progression des guides

Chaque guide du parcours commence par une section **Repères de progression** avec les mêmes huit informations :

1. **Pour qui** — toujours toute personne suivant le parcours ;
2. **Position dans le parcours** — par exemple `5/14` ;
3. **Prérequis** — ce qui doit déjà avoir été lu ou compris ;
4. **Objectif** — ce que la page enseigne ;
5. **Résultat attendu** — ce que le lecteur doit savoir faire ou expliquer après lecture ;
6. **Critère d'arrêt** — quand il ne faut pas poursuivre mécaniquement ;
7. **Continuer avec** — l'étape suivante du même parcours ;
8. **Source de vérité** — le contrat, le code ou la preuve qui décide réellement.

Ce contrat est vérifié par la CI. Une future modification ne doit pas recréer des niveaux de lecteurs ou plusieurs chemins documentaires concurrents.

## Accès direct par besoin

Le parcours ci-dessus reste la référence pour apprendre le projet de bout en bout. Une personne qui connaît déjà le sujet recherché peut néanmoins accéder directement à un document :

| Besoin immédiat | Document |
|---|---|
| comprendre les premières commandes et les états | [`GETTING_STARTED.md`](GETTING_STARTED.md) |
| installer la plateforme | [`INSTALLATION.md`](INSTALLATION.md) |
| exploiter la plateforme au quotidien | [`OPERATIONS.md`](OPERATIONS.md) |
| diagnostiquer une anomalie | [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) |
| comprendre l'architecture Linux | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| comprendre les huit agents et leur routage | [`MULTI_AGENT_CORE.md`](MULTI_AGENT_CORE.md) |
| comprendre le moteur de projets | [`PROJECT_ENGINE.md`](PROJECT_ENGINE.md) |
| comprendre le Gateway `systemd --user` | [`OPENCLAW_SYSTEMD.md`](OPENCLAW_SYSTEMD.md) |
| comprendre le cycle de vie complet | [`LIFECYCLE.md`](LIFECYCLE.md) |
| comprendre la pile B580 / `xe` / Vulkan | [`FEDORA_B580.md`](FEDORA_B580.md) |
| comprendre la politique kernel | [`KERNEL_POLICY.md`](KERNEL_POLICY.md) |
| mettre à jour OpenClaw, Ollama, modèles, Mesa ou kernel | [`UPGRADE.md`](UPGRADE.md) |
| qualifier Fedora et l'Intel Arc B580 | [`QUALIFICATION.md`](QUALIFICATION.md) |
| consulter les étapes L0–L8 | [`ROADMAP.md`](ROADMAP.md) |
| connaître l'état réel du dépôt | [`../STATUS.md`](../STATUS.md) |
| contribuer au code | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) |
| consulter la politique sécurité | [`../SECURITY.md`](../SECURITY.md) |

Un accès direct est un raccourci de consultation, **pas un second parcours pédagogique**.

## Vérités canoniques

Pour éviter les divergences documentaires :

1. **identités modèles** → `config/model_catalog.yaml` ;
2. **versions runtime** → `config/runtime_versions.yaml` ;
3. **routage agents** → `config/core/model_routing.yaml` ;
4. **outils agents** → `config/core/tool_policy.yaml` ;
5. **qualification** → `config/qualification_policy.yaml` ;
6. **optimisation L6** → `config/optimization_policy.yaml` ;
7. **release readiness** → `config/release_readiness.yaml`.

Une documentation ne doit jamais devenir une seconde configuration cachée.

## Invariant critique

Une CI verte démontre la cohérence logicielle du dépôt. Elle ne démontre pas la qualification réelle de Fedora 44, de l'Intel Arc B580, de Vulkan, des performances HARD-40M/L6 ni l'approbation V1. Ces preuves sont produites sur la machine cible et restent soumises aux gates prévus.
