# Plan : tout faire depuis Open WebUI

**Statut : plan du 9 octobre 2026. Le lot 9 est implémenté ; les autres lots ne le sont pas encore.** Ce document est mis à jour à chaque lot : une case n'est cochée que si la preuve annoncée existe.

## 1. Objectif

Aujourd'hui, le chat Open WebUI et l'atelier Projets sont deux interfaces séparées : le chat ne connaît aucun projet, ne peut pas y écrire et ne peut rien approuver. L'objectif est qu'on puisse **tout faire depuis Open WebUI** : choisir un projet, l'interroger, faire générer ses documents, le créer, le planifier, l'exécuter, l'auditer et le livrer. L'atelier reste disponible, comme une autre vue du même moteur.

## 2. Principe : une seule source de vérité

Le chat n'a **aucun état de projet à lui**. Chaque action du chat appelle les **mêmes fonctions et les mêmes garde-fous** que l'atelier (`project_ui`, `project_engine`, `project_worker`) : états du projet, plan, verrou, collecteur de fichiers, vérification des chemins, audit indépendant, accord cloud par projet, pause visible. Ce qu'on fait dans le chat apparaît dans l'atelier, et inversement.

## 3. Décisions

| Sujet | Décision | Pourquoi |
|---|---|---|
| Comment piloter | **Commandes** comprises par le pont lui-même (code déterministe), jamais par le modèle. | Un modèle peut se tromper ou être manipulé par un document ; un changement d'état de projet ne doit pas dépendre de son interprétation. |
| Préfixe | `!` (ex. `!projets`, `!projet mon-projet`). `/` est accepté si Open WebUI le laisse passer. | Open WebUI utilise `/` et `@` pour ses propres raccourcis. Ce comportement n'a pas pu être vérifié ici : à confirmer au test de fumée. |
| Projet courant | Rappelé par un **marqueur** en tête des réponses du pont (`📁 Projet : id`), relu dans l'historique du fil. | Le pont est sans mémoire entre deux messages, comme pour le marqueur « conversation passée en local ». |
| Approbation | **Phrase de confirmation à usage unique**, générée par le pont (pas par le modèle) : `approuver plan K7Q2`. Valable seulement si elle est **le dernier message de l'utilisateur**, que le code correspond à un état enregistré côté serveur, qu'il n'a pas expiré (15 minutes) et que ce qu'on approuve n'a pas changé (empreinte SHA-256). | Le modèle ne peut ni produire ni valider une approbation : une consigne cachée dans un document ne peut pas approuver à sa place. Les décisions restent les vôtres. |
| Actions longues | Lancées **en arrière-plan** : le chat répond « lancé » et `!état` donne l'avancement. Une seule génération à la fois (verrou existant). | Une tâche prend plusieurs minutes : une requête de chat tiendrait mal. |
| Documents joints | Le pont ne reçoit que du **texte**. Pour importer des PDF ou DOCX : coller le texte, ou déposer les fichiers dans un dossier d'import local puis `!importer nom`. | C'est une limite du pont actuel, gardée par sécurité (taille, types). |
| Cloud | Le contexte d'un projet n'est envoyé au cloud que si le modèle « · cloud » est choisi **et** que le projet a l'**accord cloud valide** ; sinon le pont le dit et propose le modèle local ou l'accord (par phrase de confirmation). Filtre, budget et pause visible s'appliquent comme dans l'atelier. | Même règle partout. |
| Documents produits dans le chat | Arrivent dans le projet comme **propositions** ; on les accepte par phrase de confirmation ; l'audit indépendant reste obligatoire. | Le niveau d'autorité du chat n'est pas supérieur à celui de l'atelier. |

## 4. Lots

Une branche et une pull request en brouillon par lot ; aucune fusion automatique ; chaque PR dit ce que la CI prouve et ce qu'elle ne prouve pas.

| Lot | Contenu | État |
|---|---|---|
| 9 | **Lire** : `!projets`, `!projet`, `!état`, `!quitter`. Questions sur un projet : le rôle reçoit un contexte en lecture seule (résumé, plan, décisions, extraits retrouvés par la recherche locale). Accord cloud respecté. | [x] cette PR |
| 10 | **Approuver et produire** : phrase de confirmation à usage unique ; documents générés dans le chat enregistrés comme propositions du projet ; `!propositions`, `!accepter`, `!refuser`. | [ ] |
| 11 | **Créer et cadrer** : `!créer`, cadrage, clarifications, plan court, approbations par phrase de confirmation. | [ ] |
| 12 | **Conduire** : exécution en arrière-plan, pause et reprise, audits, pratique guidée et retour, modification cohérente, livraison finale. | [ ] |
| 13 | **Importer et documenter** : import de documents par dossier local, schéma, guide, fiches, captures, test de fumée. | [ ] |

## 5. Ce que chaque lot doit prouver

- Des tests contre le pont avec un client qui imite Open WebUI (requêtes OpenAI-compatibles), pour chaque commande, y compris les refus.
- **Aucune approbation sans phrase valide** : essais avec un faux code, un code expiré, un code déjà utilisé, un code d'un autre projet, un contenu modifié entre la proposition et l'approbation, une approbation écrite par l'assistant ou cachée dans un document.
- **Le chat ne contourne rien** : mêmes états, mêmes verrous, mêmes vérifications de chemins que l'atelier ; aucun projet gardé n'est modifié par une simple conversation.
- Cloud : un projet sans accord n'envoie jamais son contenu au cloud depuis le chat.
- Le comportement de l'atelier ne change pas (tests existants).

## 6. Ce qui ne sera pas prouvé ici

Ce qui dépend de l'interface réelle d'Open WebUI : le traitement des préfixes `/` et `@`, l'affichage des liens et des messages de confirmation, les délais d'attente sur de longues réponses, le rendu du Markdown. Il n'y a pas d'Open WebUI dans l'environnement de développement : ces points sont **vérifiés au test de fumée sur votre PC**, avec la liste des cas à essayer fournie dans le lot 13.

## 7. Limites assumées dès maintenant

- Le chat ne pourra pas importer directement un fichier joint (voir « Documents joints »).
- Pendant qu'une tâche tourne, le chat répond « occupé » : une seule génération à la fois, comme aujourd'hui. `!état` reste disponible.
- L'approbation par phrase est plus lourde qu'un clic : c'est le prix de la sécurité.
