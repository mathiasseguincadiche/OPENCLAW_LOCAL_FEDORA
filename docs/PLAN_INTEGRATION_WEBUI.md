# Plan : tout faire depuis Open WebUI

**Statut : implémentation révisée le 10 octobre 2026. Les lots 9 à 15 sont implémentés dans le dépôt.** Les tests automatiques couvrent le pont, les garde-fous, les uploads et le service vocal ; le test de fumée sur le vrai PC Fedora reste nécessaire pour valider l'ergonomie, le micro, la latence et le stockage réel d'Open WebUI.

## 1. Objectif

Aujourd'hui, le chat Open WebUI et l'atelier Projets sont deux interfaces séparées : le chat ne connaît aucun projet, ne peut pas y écrire et ne peut rien approuver. L'objectif est qu'on puisse **tout faire depuis Open WebUI** : choisir un projet, l'interroger, faire générer ses documents, le créer, le planifier, l'exécuter, l'auditer et le livrer. Le chat doit être **complet** : on y joint des fichiers (PDF, Office, archives, code), des images, et on peut **parler** (note vocale) au lieu de taper. L'atelier reste disponible, comme une autre vue du même moteur.

## 2. Principe : une seule source de vérité

Le chat n'a **aucun état de projet à lui**. Chaque action du chat appelle les **mêmes fonctions et les mêmes garde-fous** que l'atelier (`project_ui`, `project_engine`, `project_worker`) : états du projet, plan, verrou, collecteur de fichiers, vérification des chemins, audit indépendant, accord cloud par projet, pause visible. Ce qu'on fait dans le chat apparaît dans l'atelier, et inversement.

## 3. Décisions

| Sujet | Décision | Pourquoi |
|---|---|---|
| Comment piloter | **Commandes** comprises par le pont lui-même (code déterministe), jamais par le modèle. | Un modèle peut se tromper ou être manipulé par un document ; un changement d'état de projet ne doit pas dépendre de son interprétation. |
| Préfixe | `!` (ex. `!projets`, `!projet mon-projet`). `/` est accepté si Open WebUI le laisse passer. | Open WebUI utilise `/` et `@` pour ses propres raccourcis. Ce comportement n'a pas pu être vérifié ici : à confirmer au test de fumée. |
| Projet courant | Rappelé par un **marqueur** en tête des réponses du pont (`📁 Projet : id`), relu dans l'historique du fil. | Le pont est sans mémoire entre deux messages, comme pour le marqueur « conversation passée en local ». |
| Approbation | **Phrase de confirmation à usage unique**, générée par le pont (pas par le modèle) : `approuver proposition K7Q2`. Valable seulement si elle est **le dernier message de l'utilisateur**, que le code correspond à un état enregistré côté serveur, qu'il n'a pas expiré (15 minutes) et que ce qu'on approuve n'a pas changé (empreinte SHA-256). | Le modèle ne peut ni produire ni valider une approbation : une consigne cachée dans un document ne peut pas approuver à sa place. Les décisions restent les vôtres. |
| Actions longues | Lancées **en arrière-plan** : le chat répond « lancé » et `!état` donne l'avancement. Une seule génération à la fois (verrou existant). | Une tâche prend plusieurs minutes : une requête de chat tiendrait mal. |
| Fichiers joints | Un fichier joint dans le chat est **enregistré tel quel** dans le projet courant (ou, sans projet, dans une zone d'import du chat), puis lu par la **même chaîne d'ingestion que l'atelier** (types, tailles, archives sûres, couverture de lecture READ/PARTIAL/UNREADABLE). Rien n'est lu « à moitié » en silence : le chat annonce ce qui a été lu et ce qui ne l'a pas été. | Une seule chaîne de lecture, déjà éprouvée ; pas de seconde chaîne RAG dans Open WebUI. |
| Images | Les images jointes sont transmises au rôle local (Qwen 3.5 est multimodal : entrée image déclarée dans `model_catalog.yaml`), après contrôle du type réel (signature de fichier), de la taille et des dimensions. **Jamais envoyées au cloud pour l'instant** : DeepSeek V4.1 Flash sait accepter des images, mais le filtre de confidentialité du projet ne sait pas inspecter leur contenu. Tant que ce contrôle n'existe pas, une image reste locale. | Le filtre protège tout ce qui part au cloud ; ce qu'il ne peut pas inspecter ne part pas. |
| Voix | Note vocale = **dictée locale** : l'audio est transcrit sur la machine (Whisper local), jamais par un service du navigateur qui l'enverrait à un tiers. Le texte transcrit arrive dans la zone de saisie, **relu avant l'envoi**. Réponses lues à voix haute par une synthèse vocale **locale** (option). Le mode appel mains libres (envoi sans relecture) reste désactivé. | Vie privée (rien ne sort), et une phrase d'approbation mal entendue ne doit jamais partir sans relecture. |
| Approbation et voix | Une phrase d'approbation n'est valable que **tapée ou dictée puis envoyée par vous** ; elle est à usage unique et liée à un code que le modèle ne produit pas. | Même sécurité qu'à l'écrit. |
| Cloud | Le contexte d'un projet n'est envoyé au cloud que si le modèle « · cloud » est choisi **et** que le projet a l'**accord cloud valide** ; sinon le pont le dit et propose le modèle local ou l'accord (par phrase de confirmation). Filtre, budget et pause visible s'appliquent comme dans l'atelier. | Même règle partout. |
| Documents produits dans le chat | Arrivent dans le projet comme **propositions** (`!garder`) ; acceptées par phrase de confirmation, elles deviennent des **notes** (`context/chat/notes`), jamais des livrables. Un livrable naît d'une tâche du plan et passe l'audit indépendant, comme dans l'atelier (lot 12). | Le niveau d'autorité du chat n'est pas supérieur à celui de l'atelier ; un texte écrit par un modèle n'entre pas dans le paquet final sans audit. |

## 4. Lots

Une branche et une pull request en brouillon par lot ; aucune fusion automatique ; chaque PR dit ce que la CI prouve et ce qu'elle ne prouve pas.

| Lot | Contenu | État |
|---|---|---|
| 9 | **Lire** : `!projets`, `!projet`, `!état`, `!quitter`. Questions sur un projet : le rôle reçoit un contexte en lecture seule (résumé, plan, décisions, extraits retrouvés par la recherche locale). Accord cloud respecté. | [x] |
| 10 | **Approuver et produire** : phrase de confirmation à usage unique ; documents générés dans le chat enregistrés comme propositions du projet ; `!propositions`, `!accepter`, `!refuser`. | [x] |
| 11 | **Créer et cadrer** : `!creer` (la demande est le message précédent), `!analyser`, `!questions`/`!repondre`, `!planifier`, `!valider` ; création, analyse et plan approuvés par phrase de confirmation ; brouillons rédigés en arrière-plan. | [x] |
| 12 | **Conduire** : `!lancer`, `!pause`, `!reprendre`, audits, pratique guidée (`!pratique`, `!soumettre`), modification cohérente avec confirmation et livraison finale avec confirmation. | [x] |
| 13 | **Pièces jointes** : filtre Open WebUI géré, copie contrôlée du fichier original, même chaîne d'ingestion que l'atelier, sources figées après analyse ; images locales uniquement. | [x] |
| 14 | **Voix** : STT Whisper local CPU/int8, TTS local, service loopback protégé par jeton ; appel mains libres désactivé. | [x] |
| 15 | **Importer, documenter, tester** : dossier d'import local de secours (`!importer`), documentation, architecture et checklist de test de fumée. | [x] |

## 5. Ce que chaque lot doit prouver

- Des tests contre le pont avec un client qui imite Open WebUI (requêtes OpenAI-compatibles), pour chaque commande, y compris les refus.
- **Aucune approbation sans phrase valide** : essais avec un faux code, un code expiré, un code déjà utilisé, un code d'un autre projet, un contenu modifié entre la proposition et l'approbation, une approbation écrite par l'assistant ou cachée dans un document.
- **Le chat ne contourne rien** : mêmes états, mêmes verrous, mêmes vérifications de chemins que l'atelier ; aucun projet gardé n'est modifié par une simple conversation.
- Cloud : un projet sans accord n'envoie jamais son contenu au cloud depuis le chat.
- Le comportement de l'atelier ne change pas (tests existants).

- **Pièces jointes** : un fichier piégé (archive qui s'extrait hors du dossier, bombe de décompression, lien symbolique, faux type d'image, texte contenant des ordres) est refusé ou traité comme **donnée sans autorité** ; la taille et le nombre sont bornés ; un fichier joint ne quitte jamais la machine sans l'accord cloud du projet, et une image ne part jamais au cloud.
- **Voix** : aucune dépendance à un service externe (vérifié par la configuration générée : moteur local, mode hors ligne) ; aucun envoi automatique en mode appel.

## 6. Ce qui ne sera pas prouvé ici

Ce qui dépend du vrai poste reste volontairement non déclaré comme acquis : le traitement des préfixes `/` et `@`, le rendu exact des confirmations et liens, le comportement du filtre global de pièces jointes dans l'image Open WebUI épinglée, la qualité du micro, la latence de Whisper et de la synthèse, ainsi que la mémoire réellement utilisée. Ces points sont vérifiés avec [SMOKE_TEST_WEBUI.md](SMOKE_TEST_WEBUI.md) sur le PC Fedora.

## 7. Limites assumées dès maintenant

- **Fichier d'origine** : un filtre Open WebUI global désactive son RAG pour cette route et transmet au pont uniquement une référence au fichier appartenant à l'utilisateur. Le pont résout ensuite le fichier dans le volume local `uploads/`, contrôle chemin, taille et nom, puis le copie dans l'ingestion canonique. Le dossier `state/chat-import/inbox/<projet>` reste le plan B si le comportement réel de la version épinglée diffère.
- **Sources immuables** : les uploads de cadrage ne sont acceptés qu'en `INTAKE_READY`. Après analyse, une pièce jointe ne peut pas changer silencieusement les sources ni rendre l'accord cloud obsolète.
- **Pas d'image au cloud** : les images sont ingérées localement ; tant que le filtre de confidentialité ne sait pas inspecter leur contenu, elles ne sont pas routées vers DeepSeek.
- **Voix** : la qualité du français et la vitesse dépendent du modèle Whisper choisi et se mesurent sur le PC ; la synthèse vocale locale est une option, pas une promesse de voix naturelle.
- Pendant qu'une tâche tourne, le chat répond « occupé » : une seule génération à la fois, comme aujourd'hui. `!état` reste disponible.
- L'approbation par phrase est plus lourde qu'un clic : c'est le prix de la sécurité.
