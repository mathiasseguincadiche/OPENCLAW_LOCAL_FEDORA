# Documentation de l’Atelier IA

**Point d’entrée unique** : cette page oriente vers la procédure adaptée à ton besoin, sans demander de lire toute l’architecture. L’environnement cible est **Fedora 45 Workstation / GNOME 51**, avec les données de l’atelier sur le volume secondaire **`/IA/Openclaw/`**.

## Commencer simplement

| Je veux… | Ouvrir |
| --- | --- |
| Comprendre le projet en quelques minutes | [Présentation](../README.md) puis [Guide de découverte](GUIDE.md) |
| Installer Fedora et l’atelier | [Installation simple et vérification unique](INSTALLATION_SIMPLE_FEDORA45.md) |
| Vérifier que mon installation fonctionne | [Premiers essais](fiches/02-premier-essai.md) : **`./menu.sh --action quick-check`** |
| Discuter avec Qwen | [Fiche 03 — Discussion](fiches/03-discuter.md) |
| Créer ou reprendre un projet | [Fiche 04 — Atelier Projets](fiches/04-atelier-projets.md) |
| Savoir ce qui est réellement testé | [État et limites](../STATUS.md) |
| Comparer la pédagogie DeepSeek/Qwen/Gemini sur 20 | [Conversations pédagogiques et grille 5/5](EVALUATION_PEDAGOGIE.md) |

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

- [Architecture hybride Qwen / DeepSeek](ARCHITECTURE_HYBRIDE.md) et [schémas éditables](diagrams/).
- [Audit transversal de la documentation — 20 octobre 2026](AUDIT_DOCUMENTATION_2026_10.md) (43 pages préexistantes revues, corrections et limites de preuve).
- [Qualification pédagogique et comparaison des conversations](EVALUATION_PEDAGOGIE.md) (score humain /20 ; pas de validation d'un modèle par la CI).
- [Références d’ingénierie](reference/README.md) : intégrité des composants, sécurité, cloud, prompts, fonctionnement interne.
- [Réception et tests avancés facultatifs](validation/README.md) : GPU, WebUI, voix, sauvegardes, qualité des agents.
- [Parcours DevOps de démonstration](EXEMPLE_PARCOURS_DEVOPS.md) : exemple pédagogique et non preuve d’un déploiement réel.
- [Plans, audits et décisions historiques de 2026](archives/2026/README.md).

## Contribuer et vérifier

[Contribuer](../CONTRIBUTING.md) · [Politique de sécurité](../SECURITY.md) · [Historique des changements](../CHANGELOG.md) · [Code source](../src/) · [Scripts](../scripts/) · [Tests](../tests/)

**Règle de lecture** : un test de CI réussi n’équivaut pas à une réception du logiciel sur le PC Fedora/Intel Arc B580. Les fonctions facultatives ou expérimentales sont identifiées comme telles.
