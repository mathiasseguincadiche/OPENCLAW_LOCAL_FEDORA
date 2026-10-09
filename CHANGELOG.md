# Historique des versions

Ce fichier suit le format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et la numérotation [SemVer](https://semver.org/lang/fr/). La version courante est dans le fichier `VERSION`.

## [Non publié]

### Ajouté
- **Interroger un projet depuis Open WebUI, en lecture seule** : commandes `!projets`, `!projet`, `!etat`, `!quitter`, `!aide`, comprises par le pont et jamais par le modèle ; le projet sélectionné est rappelé par un marqueur en tête des réponses ; le rôle reçoit un contexte borné en lecture seule. L'accord cloud du projet s'applique à tout le fil.

- **Garder et accepter un document depuis le chat** : `!garder`, `!propositions`, `!voir`, `!accepter`, `!refuser`. Une proposition acceptée devient une **note** du projet (jamais un livrable), uniquement avec une **phrase de confirmation** (`approuver proposition K7Q2`) générée par le pont : à usage unique, valable 15 minutes, liée à l'empreinte du contenu, valable seulement comme dernier message de l'utilisateur, jamais visible du modèle. Cinq codes faux annulent les codes en attente.

- **Créer et cadrer un projet depuis le chat** : `!creer`, `!analyser`, `!planifier`, `!valider`, `!questions`, `!repondre`. Le chat appelle les mêmes fonctions que l'atelier (`project_ui`, donc les mêmes garde-fous). La création, l'analyse et le plan s'approuvent par phrase de confirmation (`approuver creation|analyse|plan K7Q2`), liée à l'empreinte du contenu ; les brouillons du chef d'opérations sont rédigés en arrière-plan avec `!etat` pour suivre, y compris la pause cloud d'un projet autorisé. Le texte d'un modèle affiché par le pont n'a ni lien, ni image, ni phrase d'approbation copiable.

### Modifié
- README : la section « Aperçu » (captures de l'atelier avec des données d'exemple) est retirée, ainsi que les trois images.

### Corrigé
- Une réponse de modèle qui commençait comme un en-tête du pont (`📁 Projet : …`) pouvait choisir un projet pour la suite du fil : ces débuts de réponse sont désormais neutralisés.
- Le bandeau « contexte allégé » d'un long fil pouvait cacher les marqueurs de provenance et de bascule locale ; il passe maintenant après eux.

Les autres corrections viendront des premiers essais sur le PC Fedora.

## [0.1.0] - 2026-10-09

Première version complète. **Elle n'a pas encore tourné sur le PC cible** et le cloud n'a jamais été essayé avec le vrai OpenRouter : voir [STATUS.md](STATUS.md).

### Ajouté
- **Atelier local** : Qwen 3.5 9B par Ollama, sept rôles OpenClaw (mentor, recherche, architecte, DevOps, sécurité, rédacteur, auditeur), chat Open WebUI et atelier Projets, avec fichiers réels (Markdown, PDF, DOCX, YAML, Terraform, schémas Draw.io).
- **Cloud facultatif** (GLM-5.3 Flash par OpenRouter), désactivé par défaut :
  - une passerelle locale qui filtre tout ce qui part (historique et résultats d'outils compris) et qui seule détient la clé du fournisseur ;
  - un budget de 25 € réels par mois : réservation avant chaque appel, comptage de tous les appels, alerte à 80 %, arrêt au plafond ;
  - une activation contrôlée : le cloud ne s'allume que si le filtre et le budget fonctionnent ensemble ;
  - dans le chat, les modèles « · local » (mode Travail) et « · cloud (GLM) » (mode Apprendre), avec repli visible vers le local ;
  - dans l'atelier, un accord par projet lié à ses sources, une pause visible au lieu d'une bascule silencieuse, le modèle et le coût affichés.
- Consignes des rôles V2.3 avec contrôles de taille et de contrat.
- Documentation : un guide, douze fiches, la décision de modèle avec ses sources, une présentation illustrée de 17 pages et des captures de l'interface avec des données d'exemple.
- Fichiers de projet : licence MIT, contribution, sécurité, code de conduite.

### Modifié
- L'attente de l'installation porte sur les huit outils du plugin.
- Les sauvegardes n'emportent plus la clé du fournisseur ni le jeton local de la passerelle.
- La CI ne cible plus que `main`.

### Sécurité
- Un oubli corrigé avant toute utilisation : la sauvegarde, non chiffrée, emportait `state/cloud/upstream.key`. Les fichiers `*.key`, `*.token` et `*.tmp` de `state/cloud` en sont exclus.

[Non publié]: https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/releases/tag/v0.1.0
