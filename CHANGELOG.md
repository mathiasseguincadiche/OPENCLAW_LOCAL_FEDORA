# Historique des versions

Ce fichier suit le format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et la numérotation [SemVer](https://semver.org/lang/fr/). La version courante est dans le fichier `VERSION`.

## [Non publié]

### 27 octobre 2026 — audit de maturité et documentation simplifiée

- Audit du code source, des scripts, des protections et des interfaces sur la référence fusionnée #155 ; défauts reproduits et priorités distinctes des limites encore à mesurer sur le PC.
- README raccourci : présentation, interfaces, essai Live USB, installation et liens utiles. Les commandes complètes d'installation restent dans les guides opérationnels.
- Parcours documentaire aligné sur le premier essai matériel en Live USB Fedora 45 / GNOME 51, sans le présenter comme un test complet de l'atelier ; blocs Markdown du guide Live réparés et calendrier Fedora sourcé.
- État des preuves actualisé, ODT rappelé dans le guide, version du canary SSE et métadonnées de stockage corrigées ; tests de navigation adaptés à la suppression des recettes dupliquées.
- Cette révision documente les anomalies ; elle ne les corrige pas dans le moteur ou les scripts de maintenance.

### 24 octobre 2026 — parcours WebUI et visibilité du travail

- Six raccourcis regroupés : sélection visuelle du projet conservée dans le fil sans effacer la réponse, état et prochaine étape, activité, création et menus d’actions/aide.
- Vue locale authentifiée en lecture seule pour les métadonnées et l’activité ; aucun historique, document ou jeton opérateur transmis à cette consultation, aucun modèle appelé.
- Atelier Projets : un sélecteur commun au dossier, aux recherches et aux décisions ; résultats tardifs d’un autre projet ignorés, prochaine étape affichée, raisons d’indisponibilité et temps écoulé connu. Le formulaire de création se replie lorsque des projets existent.
- Confirmations, phrases à usage unique, filtrage cloud et verrou de génération conservés. Streaming et arrêt effectif restent un chantier distinct à qualifier sur Fedora.

### 23 octobre 2026 — documents OpenDocument (ODT)

- Export ODT éditable depuis la même source Markdown que PDF/DOCX/TXT : titres, paragraphes, listes, citations, tableaux simples et code, sans nouvelle dépendance de production.
- Format raccordé à l’outil des sept rôles, aux liens de téléchargement du chat, aux projets et à l’assemblage de sections, avec empreintes et contrôle de la source.
- Import textuel ODT local en chat et dans les projets ; bornes ZIP/XML, refus des documents chiffrés ou mal formés, sans chargement de ressources externes ni exécution de macros.
- Consignes, README, fiches et schéma des rôles (SVG/Draw.io) harmonisés. Le Markdown reste la source canonique ; l’import ne préserve pas la présentation ni les images.

### 22 octobre 2026 — cohérence de la documentation après la PR #152

- Harmonisation du parcours README → installation → premier essai : `quick-check` suffit pour commencer ; la réception 32K reste volontaire et nécessaire pour déclarer cette capacité mesurée.
- Correction des dernières références actives à `/IA/Openclaw` et au clonage dans le dossier personnel ; les sources sont sous `/data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA` et les données restent hors du dépôt Git.
- Synchronisation des sources Draw.io avec les aperçus SVG : Qwen local, DeepSeek cloud sur accord, passerelle et sept rôles ; les blocs, textes et flèches restent éditables.
- Actualisation de `STATUS.md` avec les liens de CI et CodeQL réussis après fusion de la PR #152. Les anciens chemins et versions des entrées datées ci-dessous restent historiques.

### 22 octobre 2026 — stockage `/data` et sécurité PDF — PR #152

- Configuration commune `config/storage.json` : volume EXT4 distinct monté sur `/data`, runtime `/data/IA/Openclaw`, seuils d'espace libre sur les deux SSD et UUID facultatif. Scripts et services refusent l'absence du disque et les redirections interdites.
- Stockage Podman privé pour les images et couches Open WebUI sur le SSD secondaire, avec permissions et contextes SELinux dédiés ; configuration des autres conteneurs conservée.
- Dépendance PDF `pypdf` passée de 6.19.0 à 6.21.2 avec ses empreintes corrigées, à la suite des avis de sécurité détectés par Dependency Review ; aucun avis ignoré.
- Guides de stockage, installation et sauvegarde mis à jour. Les régressions automatisées passent ; la réception réelle Fedora/B580, WebUI et restauration reste à effectuer.

### 21 octobre 2026 — pré-check obligatoire et recette Qwen 32K

- Ajout de `./menu.sh --action precheck` (sans installation) : Fedora 45/GNOME 51/Wayland, stockage `/IA`, Ryzen, RAM, B580/pilote `xe`, SELinux, UEFI, session systemd, dépendances installables et Internet. Le contrôle est relancé automatiquement par `install --apply` **avant toute installation de paquets**.
- Ajout d'une réception **volontaire après l'installation WebUI** : `./menu.sh --action acceptance-32k --apply`, qui combine `quick-check` et un test Qwen proche de 32 768 tokens avec preuve de remplissage et de VRAM ; défauts de troncature, absence de réponse et offload CPU explicitement refusés.
- Correction des droits d'exécution Git de huit scripts Fedora. La CI contrôle désormais que les scripts appelés directement sont exécutables, afin d'éviter `Permission denied` sur un clonage frais.
- Guides et tests de non-régression synchronisés ; les contrôles du menu reconnaissent les actions avec chiffres comme `acceptance-32k` et l'ordre pré-check puis installation.
- **Aucun succès matériel réel n'est encore déclaré** ; le test 32K requiert une génération locale explicitement demandée sur Fedora.



### 21 octobre 2026 — validation du premier démarrage à partir du README

- Relecture du chemin README → `menu.sh` → installation Fedora → Open WebUI → `quick-check` et activation cloud facultative.
- Ajout du prérequis `git` avec installation conditionnelle sous Fedora 45, et clonage explicitement dans le dossier personnel.
- Correction du guide qui lançait `validate` avant l'installation des dépendances Python (dont PyYAML) ; désormais exécutable après bootstrap.
- Clarification de la différence entre aperçu `install` et qualification réelle des prérequis, des droits `sudo`, du montage `/IA` et des points d'entrée CLI.
- Après déconnexion/reconnexion GNOME (groupes GPU), ajout du `cd "$HOME/OPENCLAW_LOCAL_FEDORA"` avant `webui-install`, pour éviter l'appel de `./menu.sh` depuis un nouveau terminal ouvert au mauvais endroit.
- Le service système Ollama obtient explicitement les groupes périphériques `render` et `video` dans son unité systemd, conformément au besoin d'accès GPU de son compte propre, sans ajout permanent de groupes à ce compte ; test et diagnostic associé.
- Tests empêchant la réapparition de ces erreurs dans les guides destinés à une installation vierge.



### 20 octobre 2026 — sécurité Pillow en sortie d'audit documentaire

- Dependency Review a signalé huit CVE sur Pillow 12.3.0 ; mise à jour de la dépendance directe et du verrou Python vers **Pillow 13.0.0**, version corrective indiquée par `pip-audit`.
- SHA-256 revus pour les wheels Linux x86_64 Python 3.12/3.13 et l'archive source (références publiques PyPI du 16 octobre 2026), sans désactiver la vérification des hashes ni élargir les permissions du système.
- Mise à jour du test de verrou ; recette CI complète à exécuter avant fusion.


### 20 octobre 2026 — audit transversal et synchronisation documentaire

- Revue transversale des 43 pages Markdown de `docs/` en place avant cette PR : navigation, versions, commandes de base, archives et liens aux sources de vérité.
- Mise à jour de `STATUS.md` (référence CI #148), du guide d'installation (sauts de ligne), et du guide d'intégrité Python (verrou réel des outils de build).
- Documentation consolidée des sept champs du mentor, des évaluations pédagogiques /20 et des contrôles de réception Fedora/OpenRouter ; archives historiques conservées.
- Ajout de tests de non-régression pour les commandes du menu, les références pédagogiques et les lignes d'installation, plus un rapport d'audit transparent sur les limites de la vérification.



### 20 octobre 2026 — qualification pédagogique multi-tours et préférences du mentor

- Nouvelle suite hors ligne `clawfedora-pedagogy`: quatre critères 0–5, quatre scénarios de trois tours, comparaison humaine Qwen/DeepSeek/référence externe et refus des rapports incomplets.
- Continuité volontaire: deux notes approuvées dans le tableau de bord (manière préférée d'apprendre et résumé d'acquis), sans stockage automatique ni exfiltration autonome.
- Reformulation de blocage dans les prompts communs, mentor/rédacteur et pont de chat; tests contractuels et documentation d'acceptation.
- Pas de troisième IA, pas de hausse du budget 25 €, pas de test de qualité réelle prétendu.

### 20 octobre 2026 — CI Python reproductible

- Les jobs Python 3.12/3.13, quality et native-openclaw installent les dépendances en appliquant les contraintes Python vérifiées du dépôt. Corrige la dérive `wcwidth` détectée par les tests (0.9.3 téléchargé contre 0.9.2 verrouillé), sans réécrire les empreintes de production.

### 20 octobre 2026 — pédagogie ciblée et DeepSeek V4.1 Flash 1017

- Modèle cloud épinglé à `deepseek/deepseek-v4.1-flash-1017` sans ajout de fournisseur ni changement du plafond de 25 €.
- Alignement des contrats, tests et documents sur l'identité du nouveau modèle ; endpoint réel et facturation à qualifier sur Fedora.
- Consignes du mentor et du rédacteur renforcées pour des explications courtes, concrètes, vérifiables et sans répétition inutile.
- Guide d'usage des profils d'effort manuels pour préserver le coût ; les permissions, le consentement et les garde-fous restent inchangés.

### 19 octobre 2026 — fermeture de la chaîne de construction Python

- Ajout des SHA-256 vérifiés de `setuptools 80.9.0` et `wheel 0.45.1`.
- Bootstrap Fedora, CI et service de voix : distribution binaire uniquement (`--only-binary=:all:`), `--require-hashes`, puis installation locale sans isolation PEP 517 ni résolution supplémentaire.
- Tests de modification d'empreintes et contrôle de l'installation wheel-only ; RPM et extras de développement restent hors de ce périmètre.


### 19 octobre 2026 — fermeture de dépendances appliquée à l'installation

- Fermeture npm OpenClaw/Parallel enregistrée dans `config/npm-runtime/package-lock.json` : intégrités SHA-512 et dépendances embarquées, installation `npm ci` en staging plutôt que résolution globale libre.
- Fedora 45 conserve Python 3.15 pour le système ; un venv isolé Python **3.13** est utilisé pour le runtime IA, afin de conserver la compatibilité de l'audio CTranslate2.
- Production Python : `--require-hashes` avec les SHA-256 des artefacts PyPI, suivi d'une installation du projet en `--no-deps`. CI dédiée Fedora 45 / Python 3.15.
- Les 21 dépendances optionnelles de voix sont elles aussi verrouillées par versions et SHA-256 et testées sur Fedora 45/Python 3.13 ; les RPM Fedora, les exigences PEP 517 temporaires et les extras de développement demandent encore leur propre qualification ; cette modification ne prouve pas l'installation sur le PC réel.


### Protection du disque secondaire `/IA` contre les redirections de chemins

- `claw_require_storage` refuse les chemins contenant traversées `..` ou des liens symboliques et les liens dans les dossiers sensibles (modèles, projets, configuration, services, sauvegardes). Les dossiers inexistants restent acceptés lors d'une installation neuve.
- Régressions de traversée de chemin vérifiées par des tests shell sans accès réseau ni écriture sur le disque cible. Les tests de stockage réel nécessitent toujours Fedora et le volume secondaire monté.


### Mode Web privé — transition vérifiée avant réception matérielle

- Nouveau menu `web-private` / `web-connected` : aperçu sans modification, arrêt préventif du Gateway, verrou des travaux, application native, contrôle privé du fichier de configuration et redémarrage vérifié.
- Le contrôle refuse le mauvais état des outils `web_search` et `web_fetch` dans les sept rôles, les droits de fichier trop ouverts et les chemins liés. La CI teste ces contrats sans lancer de modèle ni contacter Internet.
- La preuve d'absence effective de trafic réseau reste à faire sur Fedora ; aucun changement de fournisseur cloud ou de politique de consentement.


### 18 octobre 2026 — stockage secondaire, parcours court et refonte documentaire

- PR [#135](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/135) et [#136](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/136) : runtime et projets dans `/IA/Openclaw/` sur disque monté ; lancement des services ordonné après ce montage ; commande `quick-check` pour une réception courte, sans stress test obligatoire.
- PR [#127](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/127) à [#133](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/133) : mode Web privé explicite, migrations d’état opt-in, verrou de versions Python, vérifications Fedora 45, distinction des tests GPU 60 %/90 % et restauration synthétique de quatre projets et de la base WebUI.
- Refonte documentaire : README raccourci et hiérarchisé, sommaires utilisateur / références techniques / validations facultatives / archives, `STATUS.md` actualisé, guide de premier démarrage sans tests coûteux et références d’intégrité synchronisées.
- Les essais matériels Fedora/B580, la qualité réelle des agents et les appels/factures cloud ne sont toujours **pas** certifiés par la CI.


### 18 octobre 2026 — socle stable actualisé (qualification matérielle en attente)

- OpenClaw et plugin Parallel : 2026.10.4 ; Ollama : 0.40.6 ; Open WebUI : v0.12.3-slim dès la première installation.
- Empreintes des archives OpenClaw/Ollama reprises des publications officielles et installateur existant conservé en mode fail-closed.
- Alignement des tests de versions et du canary WebUI ; essais réels Fedora 45/B580, OpenRouter, navigateur, voix et sauvegarde non encore effectués.

### Améliorations du raisonnement DeepSeek
- Trois profils d'effort cloud bornés et enregistrés dans l'état privé : `rapide` (low/4K), `equilibre` (medium/8K), `approfondi` (xhigh/32K). Le profil par défaut reste `approfondi` pour préserver le comportement existant.
- Contrôle opérateur `cloud-profile` / `cloud-set-profile --value ... --apply`, sous verrou partagé avec le worker ; aucune modification par les agents ni paramètre libre de l'API.
- La passerelle applique le plafond de sortie avant toute réservation budgétaire et refuse tout profil local invalide. Évaluation réelle du fournisseur et du coût reportée aux tests de réception.


### Documentation du système hybride
- Le README, le guide, les rôles, le parcours DevOps, le choix de modèle et les schémas présentent désormais **Qwen 3.5 local et DeepSeek V4.1 Flash cloud comme deux moteurs complémentaires**.
- Nouvelle fiche `docs/ARCHITECTURE_HYBRIDE.md` : pourquoi DeepSeek est une **route de capacité** pour les tâches DevOps difficiles, critères de choix, parcours, consentement, budget et limites.
- Clarification essentielle : la sélection du cloud est **explicite**, l'accord s'applique au projet ; il n'existe **pas encore** de routage automatique selon la difficulté ou l'agent. Aucun nouveau comportement technique n'est annoncé comme validé sur Fedora.

### Ajouté
- **Interroger un projet depuis Open WebUI, en lecture seule** : commandes `!projets`, `!projet`, `!etat`, `!quitter`, `!aide`, comprises par le pont et jamais par le modèle ; le projet sélectionné est rappelé par un marqueur en tête des réponses ; le rôle reçoit un contexte borné en lecture seule. L'accord cloud du projet s'applique à tout le fil.

- **Garder et accepter un document depuis le chat** : `!garder`, `!propositions`, `!voir`, `!accepter`, `!refuser`. Une proposition acceptée devient une **note** du projet (jamais un livrable), uniquement avec une **phrase de confirmation** (`approuver proposition K7Q2`) générée par le pont : à usage unique, valable 15 minutes, liée à l'empreinte du contenu, valable seulement comme dernier message de l'utilisateur, jamais visible du modèle. Cinq codes faux annulent les codes en attente.

- **Créer et cadrer un projet depuis le chat** : `!creer`, `!analyser`, `!planifier`, `!valider`, `!questions`, `!repondre`. Le chat appelle les mêmes fonctions que l'atelier (`project_ui`, donc les mêmes garde-fous). La création, l'analyse et le plan s'approuvent par phrase de confirmation (`approuver creation|analyse|plan K7Q2`), liée à l'empreinte du contenu ; les brouillons du chef d'opérations sont rédigés en arrière-plan avec `!etat` pour suivre, y compris la pause cloud d'un projet autorisé. Le texte d'un modèle affiché par le pont n'a ni lien, ni image, ni phrase d'approbation copiable.

- **Conduite complète d'un projet depuis Open WebUI** : `!lancer`, `!pause`,
  `!reprendre`, `!pratique`, `!soumettre`, `!auditer`, `!relire`,
  `!modifier` et `!livrer`. Les tâches, le feedback, les audits et la livraison
  réutilisent le moteur canonique et son verrou ; les révisions et la clôture
  restent liées à une confirmation humaine à usage unique.
- **Pièces jointes Open WebUI** : filtre global réservé à l'utilisateur authentifié,
  ingestion canonique du fichier original, contrôle des chemins, empreinte SHA-256,
  refus des liens symboliques, sources figées après analyse et `!importer` comme plan B.
  Les URL d'images ne sont jamais retransmises aux modèles.
- **Voix locale** : transcription Whisper `small` CPU/int8 et synthèse `espeak-ng`,
  service loopback avec jeton privé et aucun mode d'appel mains libres.
- **Contrats et vérifications** : tests ciblés pour les commandes, les pièces jointes,
  les confirmations et l'audio ; procédure de test de fumée Fedora et vérification du cloud réel.

### Modifié
- **Documentation pédagogique** : README et guide réorganisés autour des usages réels ; description détaillée et sourcée des sept rôles, de leurs outils et de leurs limites ; parcours fictif complet de déploiement DevOps ; schémas SVG refondus pour distinguer interfaces, moteur, Qwen, cloud facultatif, données et accords humains ; contrôle automatisé des liens, noms de rôles et SVG. Cela **ne modifie pas** la version épinglée d'Open WebUI ni le niveau de validation Fedora.
- **Modèle cloud** : GLM-5.3 Flash est remplacé par **DeepSeek V4.1 Flash**, épinglé à `deepseek/deepseek-v4.1-flash` via OpenRouter. La passerelle locale, le filtre de confidentialité, le budget de 25 €, l'accord cloud par projet et le repli visible vers Qwen restent inchangés.
- Les libellés d'interface et le scope de consentement deviennent génériques à la famille DeepSeek afin que le futur passage à V4.1 Pro ne demande pas de dupliquer les sept rôles.
- Les images restent locales : V4.1 Flash est multimodal, mais le filtre de confidentialité du projet ne sait pas encore inspecter le contenu d'une image.
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
