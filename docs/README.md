# Documentation de l’Atelier IA

**Point d’entrée unique** : cette page oriente vers la procédure adaptée à ton besoin, sans demander de lire toute l’architecture. L’environnement cible est **Fedora 45 Workstation / GNOME 51**, avec les données de l’atelier sur le volume secondaire **`/data/IA/Openclaw/`**.

> **Règle de lecture :** un test de CI réussi n’équivaut pas à une réception du logiciel sur le PC Fedora/Intel Arc B580. Les fonctions facultatives ou expérimentales sont identifiées comme telles. L’état réel est dans [STATUS](../STATUS.md).

## Choisir les modèles selon le travail

[Stratégie cloud-first et qualification de Qwen](CLOUD_FIRST_QUALIFICATION.md)
explique la séparation des sept rôles, les trois niveaux de tâche,
la contre-expertise Sol approuvée et le laboratoire Kubernetes hors ligne.
Ce choix ne modifie ni le cloud désactivé par défaut ni l'accord par projet.

## Sources de projets : GitHub et Notion

[Importer un commit GitHub ou des pages Notion en lecture seule](INTEGRATION_GITHUB_NOTION.md)
explique comment créer des snapshots vérifiables, conserver la séparation
code/portfolio et formation personnelle, et protéger les notes Notion
contre un envoi cloud involontaire. L'intégration nécessite un projet
`INTAKE_READY` et une action explicite en CLI ; le chat n'interroge
pas encore les API directement.

## Construire un wiki Notion premium

La [charte universelle des wikis Notion](NOTION_WIKI_DESIGN_SYSTEM.md)
standardise la page d'accueil, les exercices, la navigation, les
illustrations et les preuves. Deux [gabarits Notion](../templates/notion/accueil-wiki.md)
sont fournis pour préparer une proposition avant validation humaine.
Les sept agents actuels sont spécialisés sur la conception, la rédaction
et l'audit. Un [éditeur Notion à portée contrôlée](NOTION_CONTROLLED_WRITES.md)
propose un diff avant modification d'un bloc textuel simple, avec consentement
humain. Le [workflow multi-blocs](NOTION_MULTI_BLOCK.md) prépare ensuite
jusqu'à cinq corrections textuelles ciblées avec inventaire et approbation
commune du plan exact ; il ne crée pas de pages et ne modifie pas les blocs riches.
Le [panneau Notion local](NOTION_DASHBOARD.md) offre la consultation des blocs,
les diffs et l'approbation humaine depuis l'atelier. Le [mode riche à
segment ciblé](NOTION_RICH_TEXT.md) préserve les annotations, les liens
voisins et les icônes/couleurs des encadrés existants.

## GitHub dans le tableau de bord et le chat

[Guide de l'intégration GitHub dans l'atelier](GITHUB_CHAT_DASHBOARD.md) : panneau local, commandes explicites Open WebUI, manifestes approuvés, captures réelles et contrôle Fedora. Aucun mot de passe n'est demandé dans le navigateur.

## Créer et protéger un dépôt GitHub

Le [guide de création GitHub et de protections](GITHUB_REMOTE_SETUP.md) présente les plans privés par défaut, les rulesets, l'audit des permissions et les limites d'accès GitHub. Les écritures nécessitent une empreinte de plan approuvée.

## Responsabilités et PR GitHub sous approbation

Le [workflow GitHub de l'atelier](GITHUB_PUBLICATION_WORKFLOW.md)
attribue les rôles : DevOps responsable du dépôt, rédacteur responsable
éditorial, auditeur pour la contre-vérification, utilisateur pour
l'autorisation et la fusion. Il documente
`clawfedora-github-scaffold` (création locale) et
`clawfedora-github-pr` (prévisualisation puis **PR brouillon** autorisée).
Sans `--apply`, aucune écriture distante n'est effectuée.

## Créer et auditer un dépôt GitHub premium

La [charte universelle GitHub](GITHUB_REPOSITORY_DESIGN_SYSTEM.md)
définit les sept gabarits, la lecture par niveaux, les schémas
Draw.io/SVG, les preuves et les protections avant PR.
L'outil local `clawfedora-github-audit --path /chemin/vers/depot`
inspecte **sans réseau ni écriture** les liens et signaux documentaires
d'un clone ou d'un snapshot GitHub importé.

Le rapport est un inventaire statique, pas une note de qualité absolue,
un état de CI, une validation de rendu GitHub ni un déploiement de VM.

## Référence métier InfraOps

[OpsDesk : architecture du laboratoire et besoins concrets des sept agents](CAS_USAGE_INFRAOPS_OPSDESK.md)
met en relation Terraform/libvirt, Rocky Linux, Docker Compose, K3s, CI/GHCR,
observabilité, restauration et preuves individuelles. La nouvelle suite
`clawfedora-evals --suite infraops --plan` fournit des cas synthétiques
spécialisés ; elle **n'exécute aucun modèle** et ne remplace pas une recette
sur Fedora.

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

- [Recette finale FinOps](validation/FINOPS.md) : budget, routage, cache et coût par tâche acceptée.

Les pages ci-dessous sont classées par **ce que tu cherches à faire**.

### Comprendre pourquoi c’est construit ainsi

- [Architecture hybride Qwen / DeepSeek / Sol](ARCHITECTURE_HYBRIDE.md) : les deux routes, le choix explicite et le schéma [`routes-inference`](diagrams/routes-inference.svg).
- [Décision de modèle](DECISION_MODELE.md) : pourquoi Qwen en local, DeepSeek en routine cloud et Sol en expertise.
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
