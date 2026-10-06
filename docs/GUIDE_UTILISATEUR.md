# Comprendre et utiliser l’Atelier IA local

**Atelier IA local — Infrastructure & OPS** est un projet personnel pour réduire la dépendance aux abonnements IA et apprendre le déploiement et l’exploitation, à partir d’un parcours d’administrateur systèmes et réseaux.

Le guide présente la configuration de référence, le choix de Qwen, les sept rôles, leurs outils réellement disponibles et le parcours complet d’utilisation. Il distingue l’aide à la compréhension, la production de son propre travail, les contrôles statiques et les preuves d’exécution.

- [Télécharger le guide PDF](guide-utilisateur.pdf) — 16 pages, édition du 6 octobre 2026.
- [Lire la source HTML imprimable](guide-utilisateur.html) — contenu du PDF, consultable hors ligne.
- [Architecture : source Draw.io](diagrams/atelier-architecture.drawio) et [aperçu SVG](diagrams/atelier-architecture.svg).
- [Rôles : source Draw.io](diagrams/atelier-roles.drawio) et [aperçu SVG](diagrams/atelier-roles.svg).

## Ce que le guide explique

1. L’origine du projet : budget, autonomie et apprentissage infrastructure/OPS.
2. La machine cible : Ryzen 7 7700, 48 Go de RAM et Arc B580 12 Go.
3. L’architecture : chat et projets, OpenClaw, Ollama, Qwen et données locales.
4. Les sept spécialités, leurs plugins et la production de documents/configurations au bon format.
5. Le mode Adaptatif, la pratique guidée et les retours avant publication.
6. L’installation, les interfaces et un premier parcours de projet.
7. Un exemple de pipeline progressif avec Git, Docker, CI et Ansible.
8. Le rôle de Terraform, du cloud et de Kubernetes selon l’exercice.
9. Les schémas Draw.io, les modifications approuvées et les dépendances.
10. Les ressources, les sauvegardes, les diagnostics et les preuves attendues.

## Utiliser et actualiser ce document

Le guide donne les repères du même [parcours commun](README.md); il ne remplace pas les procédures de référence. [INSTALLATION.md](INSTALLATION.md), [OPENWEBUI.md](OPENWEBUI.md), [LEARNING_WORKFLOW.md](LEARNING_WORKFLOW.md) et [DRAWIO.md](DRAWIO.md) détaillent les opérations. Les contrats YAML restent les sources de vérité des versions, modèles et outils.

Le PDF et le HTML sont des éditions datées. Une mise à jour de leur contenu doit conserver leur cohérence, réexporter le PDF et vérifier le rendu de toutes les pages. Le HTML contient ses styles et ses schémas vectoriels; il n’utilise aucun script, police distante ou service de génération. On peut l’ouvrir localement puis l’imprimer en PDF au format A4, avec les arrière-plans et sans les en-têtes/pieds de page du navigateur. La pagination du document est déjà intégrée.

Le guide décrit un socle logiciel testé. La vitesse, la stabilité GPU et la qualité pédagogique du modèle réel ne sont pas déduites de la CI. L’état actuel est dans [STATUS.md](../STATUS.md).
