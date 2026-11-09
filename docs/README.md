# Documentation de l’Atelier IA

**Point d’entrée unique** : cette page oriente vers la procédure adaptée à ton besoin, sans demander de lire toute l’architecture. L’environnement cible est **Fedora 45 Workstation / GNOME 51**, avec les données de l’atelier sur le volume secondaire **`/data/IA/Openclaw/`**.

> **Règle de lecture :** un test de CI réussi n’équivaut pas à une réception du logiciel sur le PC Fedora/Intel Arc B580. Les fonctions facultatives ou expérimentales sont identifiées comme telles. L’état réel est dans [STATUS](../STATUS.md).

## Commencer simplement

| Je veux… | Ouvrir |
| --- | --- |
| Comprendre le projet en quelques minutes | [Présentation](../README.md) puis [Guide de découverte](GUIDE.md) |
| Essayer Fedora sur la machine avant installation (facultatif) | [Live USB : contrôle matériel et limites](LIVE_USB_FEDORA45_PREQUALIFICATION.md) |
| Installer Fedora et l’atelier | [Installation simple et vérification unique](INSTALLATION_SIMPLE_FEDORA45.md) |
| Réceptionner l’atelier sur le PC, étape par étape | [Liste de contrôle de réception](RECEPTION_ETAPE3.md) |
| Vérifier que mon installation fonctionne | [Premiers essais](fiches/02-premier-essai.md) : **`./menu.sh --action quick-check`** |
| Discuter avec Qwen | [Fiche 03 — Discussion](fiches/03-discuter.md) |
| Créer ou reprendre un projet | [Fiche 04 — Atelier Projets](fiches/04-atelier-projets.md) |
| Savoir ce qui est réellement testé | [État et limites](../STATUS.md) |

## Les 12 fiches pédagogiques

Les fiches sont un **parcours de référence**, pas douze étapes obligatoires à exécuter.

| Découverte et utilisation | Configuration et maintenance |
| --- | --- |
| [01 — Installer](fiches/01-installer.md) | [07 — Rôles et outils](fiches/07-roles-et-outils.md) |
| [02 — Premier essai](fiches/02-premier-essai.md) | [08 — Réglages](fiches/08-reglages.md) |
| [03 — Discuter](fiches/03-discuter.md) | [09 — Entretenir et sauvegarder](fiches/09-entretenir.md) |
| [04 — Atelier Projets](fiches/04-atelier-projets.md) | [10 — Dépanner](fiches/10-depanner.md) |
| [05 — Apprendre](fiches/05-apprendre.md) | [11 — Architecture expliquée](fiches/11-comment-ca-marche.md) |
| [06 — Fichiers et schémas](fiches/06-fichiers-et-schemas.md) | [12 — Cloud facultatif](fiches/12-cloud.md) |

## Approfondir, sans alourdir le premier démarrage

Les pages ci-dessous sont classées par **ce que tu cherches à faire**.

### Comprendre pourquoi c’est construit ainsi

- [Architecture hybride Qwen / DeepSeek](ARCHITECTURE_HYBRIDE.md) : les deux routes, le choix explicite et le schéma [`routes-inference`](diagrams/routes-inference.svg).
- [Décision de modèle](DECISION_MODELE.md) : pourquoi Qwen en local et DeepSeek en option.
- [Passerelle cloud](PASSERELLE_CLOUD.md) : filtre, consentement et budget.
- [Schémas éditables](diagrams/) : les fichiers `.drawio` sont la source, les `.svg` des aperçus.

### Faire une opération précise

- [Stockage EXT4 sur `/data`, permissions et sauvegarde](STOCKAGE_DATA.md).
- [Mode Web privé ou connecté](WEB_ACCESS_PRIVATE_MODE.md) : couper ou rétablir la recherche Web des rôles.
- [Assemblage de documents professionnels](ASSEMBLAGE_DOCUMENTS.md) : `clawfedora-doc-bundle`, de sections Markdown à un livrable.
- [Parcours DevOps de démonstration](EXEMPLE_PARCOURS_DEVOPS.md) : exemple pédagogique et non preuve d’un déploiement réel.

### Consulter une référence

- [Références d’ingénierie](reference/README.md) : intégrité des composants, sécurité, cloud, prompts, fonctionnement interne.
- [Verrou Python et empreintes](PYTHON_RUNTIME_LOCK.md) et [intégrité de l’installation](INSTALLATION_INTEGRITE.md).
- [Consignes pédagogiques et contrôles](PROMPTS.md).

### Vérifier et prouver

- [Réception et tests avancés facultatifs](validation/README.md) : GPU, WebUI, voix, sauvegardes, qualité des agents.
- [Audit du code source — 27 octobre 2026](AUDIT_SOURCE_2026_10_27.md) : maturité, anomalies reproduites, priorités et périmètre du test Live.
- [Qualification pédagogique et comparaison des conversations](EVALUATION_PEDAGOGIE.md) : score humain /20, sans validation d’un modèle par la CI.
- [Preuves de CI GitHub et GitLab](PREUVES_CI_GITHUB_GITLAB.md) et [audits des dépendances](audits/2026-11-02/README.md).

### Expérimental ou historique

- Canaries facultatifs : [streaming SSE](STREAMING_SSE_PREPARATION.md), [vision locale](VISION_LOCALE_CANARY.md), [laboratoire DevOps isolé](LABORATOIRE_DEVOPS.md).
- [Plans, audits et décisions historiques de 2026](archives/2026/README.md), dont la [revue documentaire du 20 octobre 2026](archives/2026/AUDIT_DOCUMENTATION_2026_10.md) : un instantané des 43 pages alors présentes ; l’état courant est dans `STATUS.md`.

## Contribuer et vérifier

[Contribuer](../CONTRIBUTING.md) · [Politique de sécurité](../SECURITY.md) · [Historique des changements](../CHANGELOG.md) · [Code source](../src/) · [Scripts](../scripts/) · [Tests](../tests/)
