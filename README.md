# Atelier IA local — Infrastructure & OPS

<p align="center">
  <img src=".github/social-preview.svg" alt="Atelier IA local — Infrastructure & OPS : un modèle Qwen, sept rôles, Fedora et Draw.io" width="100%">
</p>

[![CI](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml)
[![CodeQL](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml)
[![Fedora 44](https://img.shields.io/badge/Fedora-44-51A2DA?logo=fedora&logoColor=white)](https://fedoraproject.org/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)

**Une IA sur ton PC pour apprendre, concevoir et vérifier des projets d’infrastructure.**

Ce projet personnel est né d’un besoin concret : réduire la dépendance aux abonnements Claude et ChatGPT, en utilisant une machine déjà disponible. Il transforme l’expérience en administration Linux et réseau en pratique DevOps infrastructure/OPS : comprendre les choix, produire son travail et vérifier les résultats.

Le moteur IA fonctionne localement. Internet peut fournir des informations récentes, avec sources et dates. Le projet ne promet ni la qualité des meilleurs modèles cloud dans tous les cas, ni une utilisation sans coût d’électricité, stockage ou services externes optionnels.

**Commencer par le [guide utilisateur](docs/GUIDE_UTILISATEUR.md) · [Télécharger le PDF](docs/guide-utilisateur.pdf) · [Lire le guide HTML](docs/guide-utilisateur.html)**

## Une architecture proportionnée

La cible est **Fedora 44, Ryzen 7 7700, 48 Go de RAM et Intel Arc B580 12 Go**, avec le pilote `xe` et Mesa/Vulkan.

- **Un seul modèle quotidien** : Qwen 3.5 9B Q4_K_M, partagé par tous les rôles.
- **Une génération à la fois** : le chat et les projets utilisent un verrou commun.
- **Sept rôles spécialisés** : seuls ceux utiles à la demande sont sollicités.
- **Un accompagnement adaptatif** : aide directe pour un sujet maîtrisé, pratique guidée pour apprendre.
- **Des outils locaux ciblés** : recherche documentaire, schémas Draw.io, documents Markdown/PDF/DOCX/TXT, fichiers techniques, contrôles statiques et rapports CI.
- **Une validation humaine** : les commandes proposées sont exécutées par l’apprenant dans son exercice; les fichiers sont relus avant publication.

Le contexte reste à 8192 tokens et la réponse à 1024 tokens. Les grandes demandes sont découpées. Gemma, Ministral et Granite servent à des expériences séparées; ils ne sont pas installés ou routés par défaut. [Profil quotidien](docs/DAILY_PROFILE.md) · [Choix du modèle](docs/MODEL_SELECTION_2026_10.md).

> **État : socle logiciel validé par CI; qualification sur la machine Fedora/B580 à produire.** Les tests logiciels ne prouvent pas la vitesse, la stabilité GPU ni la qualité pédagogique du modèle réel. [État détaillé](STATUS.md). V1 reste non approuvée.

## Les rôles et leur utilité

| Rôle | Ce qu’il apporte |
|---|---|
| Mentor infrastructure/OPS | Cadrer le besoin, partir de tes acquis et proposer une prochaine étape utile |
| Recherche | Trouver des sources actuelles et distinguer faits, hypothèses et incertitudes |
| Architecte | Comparer les options, expliquer les flux et proposer des schémas Draw.io éditables |
| DevOps | Préparer configurations, procédures, CI/CD, vérifications et retour arrière |
| Sécurité | Examiner droits, secrets, exposition et risques concrets |
| Rédacteur pédagogique | Relier les contributions et produire une documentation claire |
| Auditeur qualité | Relire les critères, les sources et les preuves dans une nouvelle session |

Un rôle est un ensemble de consignes et d’outils autour du même Qwen, pas un modèle supplémentaire en mémoire. Chaque spécialiste explique son raisonnement; le rédacteur n’est pas seul responsable de l’apprentissage. [Rôles et pédagogie](docs/AGENT_TOOLS.md) · [Plugins disponibles](docs/SPECIALIST_TOOLING.md) · [Formats des livrables](docs/FILE_OUTPUTS.md).

## Trois usages complémentaires

| Interface | Usage |
|---|---|
| **Open WebUI**, `127.0.0.1:3000` | Poser une question, comprendre un mécanisme et consulter une spécialité |
| **Atelier Projets**, `127.0.0.1:18890` | Importer les documents, approuver le plan, pratiquer, demander un retour et livrer |
| **Draw.io**, ton éditeur habituel | Modifier les blocs et connexions d’un fichier `.drawio`, puis remettre le schéma dans l’atelier |

Le chat ne modifie pas le projet central. L’atelier garde les tâches, dépendances, contributions et preuves. Après une modification approuvée, les tâches dépendantes sont reprises pour éviter une documentation périmée. [Interfaces locales](docs/OPENWEBUI.md) · [Apprendre en construisant](docs/LEARNING_WORKFLOW.md) · [Schémas Draw.io](docs/DRAWIO.md).

Une [vue d’architecture éditable](docs/diagrams/atelier-architecture.drawio) et son [aperçu](docs/diagrams/atelier-architecture.svg) décrivent le chemin commun du chat et des projets. [Schéma des rôles Draw.io](docs/diagrams/atelier-roles.drawio).

## Premier démarrage

Prérequis : Fedora 44 Workstation, SELinux Enforcing et une session utilisateur normale. L’installation utilise des droits d’administration; consulter le plan avant de l’appliquer.

```bash
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd OPENCLAW_LOCAL_FEDORA
./menu.sh --action validate
./menu.sh --action install
./menu.sh --action install --apply
./menu.sh --action health
```

`install` sans `--apply` affiche un aperçu. Pour une installation existante, suivre la [migration sauvegardée](docs/UPGRADE.md) plutôt que réinstaller à l’aveugle.

Pour l’atelier seul, garder ce terminal ouvert; Ctrl+C l’arrête :

```bash
./menu.sh --action dashboard
```

Pour le chat et l’atelier en services locaux, arrêter le tableau de bord précédent, puis installer l’option Open WebUI :

```bash
./menu.sh --action webui-install --apply
```

Créer le premier compte administrateur local, puis fermer les inscriptions avec `./menu.sh --action webui-seal --apply`. [Installation complète](docs/INSTALLATION.md) · [Configuration des interfaces](docs/OPENWEBUI.md).

## Utiliser l’atelier

1. Créer un projet avec un objectif court et les documents utiles.
2. Demander le cadrage au mentor, corriger sa proposition et l’approuver.
3. Approuver un plan court avec les spécialistes nécessaires.
4. Préparer une étape; compléter les fichiers guidés et expliquer les choix.
5. Soumettre son travail, demander le retour, puis corriger si nécessaire.
6. Passer les audits et approuver explicitement la livraison.

Les agents n’ont pas de terminal général, d’écriture native ni d’accès automatique à tes comptes cloud. ShellCheck, yamllint, PyMarkdown et Gitleaks contrôlent les textes fournis; ils ne déploient rien. Terraform, Ansible, Docker et Kubernetes sont pratiqués dans ton laboratoire ou ta CI. [Moteur de projets](docs/PROJECT_ENGINE.md) · [Contrôles infrastructure](docs/INFRASTRUCTURE_CHECKS.md).

## Documentation et maintenance

Le [parcours de documentation](docs/README.md) est commun à tous, sans connaissance préalable; le PDF et les raccourcis renvoient aux mêmes procédures. Les raccourcis suivants permettent de retrouver une procédure :

| Besoin | Document |
|---|---|
| Premiers repères | [GETTING_STARTED.md](docs/GETTING_STARTED.md) |
| Installation | [INSTALLATION.md](docs/INSTALLATION.md) |
| Exploitation et sauvegardes | [OPERATIONS.md](docs/OPERATIONS.md) |
| Diagnostic | [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Mises à niveau | [UPGRADE.md](docs/UPGRADE.md) |
| Architecture | [ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Mesures sur la machine cible | [QUALIFICATION.md](docs/QUALIFICATION.md) |

Versions verrouillées dans le dépôt : **OpenClaw et Parallel 2026.9.8, Ollama 0.35.1**, avec Open WebUI **v0.11.4-slim** en option. Ce sont les versions prévues par cette édition, pas une affirmation de dernière version disponible.

Les contrats [`config/runtime_versions.yaml`](config/runtime_versions.yaml), [`config/model_catalog.yaml`](config/model_catalog.yaml), [`config/core/model_routing.yaml`](config/core/model_routing.yaml) et [`config/core/tool_policy.yaml`](config/core/tool_policy.yaml) restent les sources de vérité. SELinux, firewalld et les endpoints locaux sont conservés. [Politique de sécurité](SECURITY.md).

Pour contribuer : `make install`, puis `make ci`. GitHub vérifie Python 3.12/3.13, les contrats Fedora 44, Ruff, mypy, les tests avec couverture, ShellCheck, CodeQL et les dépendances.

Le nom public est **Atelier IA local — Infrastructure & OPS**. `OPENCLAW_LOCAL_FEDORA` reste le nom technique du dépôt et de son dossier de clonage. Licence [MIT](LICENSE).
