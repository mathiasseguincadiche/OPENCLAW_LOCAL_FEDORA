# Discuter

[← Guide](../GUIDE.md)

Open WebUI est l'interface de discussion, à l'adresse `http://127.0.0.1:3000`. Elle sert aux questions de tous les jours, comme tu le ferais avec Claude ou ChatGPT.

## Choisir à qui tu parles

Le sélecteur de modèle en haut de la page liste les sept rôles. Tous utilisent le même Qwen : choisir un rôle change les consignes et les outils, pas le modèle. Si tu as activé le cloud, chaque rôle apparaît aussi en « · cloud (DeepSeek) » : voir plus bas.

| Tu veux | Choisis |
|---|---|
| Une question générale, une explication, un blocage | Mentor infrastructure/OPS (choix par défaut) |
| Une information récente avec ses sources | Expert recherche |
| Comparer des options, obtenir un schéma | Architecte solutions |
| Un script, un playbook, un pipeline | Ingénieur DevOps |
| Relire des droits, des secrets, une exposition réseau | Ingénieur sécurité |
| Une fiche ou un document bien rédigé | Rédacteur pédagogique |
| Une relecture critique | Auditeur qualité |

Le détail de chaque rôle est dans [Rôles et outils](07-roles-et-outils.md).

## Cloud : Apprendre ou Travail

Le cloud est facultatif et désactivé tant que tu ne l'as pas activé ([Le cloud, facultatif](12-cloud.md)). Une fois activé, le sélecteur propose chaque rôle deux fois :

| Modèle | Mode | À utiliser pour |
|---|---|---|
| « … · local » | **Travail** : Qwen sur ton PC, aucun contenu de la conversation ne part vers un modèle distant | tout ce qui est interne, professionnel ou incertain |
| « … · cloud (DeepSeek) » | **Apprendre** : DeepSeek V4.1 Flash par OpenRouter | des questions publiques, sans secret |

Le choix par défaut reste local. Une réponse cloud porte un bandeau « ☁️ Réponse du modèle cloud ». Si le filtre détecte un secret dans ton message, l'historique ou un résultat d'outil, rien ne part : la conversation passe en local (« 🔒 Conversation passée en local ») et le reste du fil y reste. Si le plafond de 25 € est atteint ou si le fournisseur est indisponible, la réponse vient du local avec un bandeau « 💻 ».

Le filtre arrête les secrets, pas un contenu confidentiel qui n'en a pas l'allure : en cas de doute, choisis « local ».

## Ce qu'il faut savoir

**La réponse arrive d'un bloc.** Open WebUI attend la fin de la génération avant d'afficher. Une réponse longue peut demander une à plusieurs minutes selon la vitesse mesurée au [premier essai](02-premier-essai.md).

**Une seule génération à la fois.** Si l'atelier Projets travaille, le chat répond qu'il est occupé, et inversement. Le modèle n'est jamais lancé deux fois en parallèle.

**La mémoire dépend de la route.** Qwen reçoit les messages récents jusqu'à 32 000 octets. DeepSeek peut recevoir un historique beaucoup plus large (jusqu'à environ 768 Ko transmis par le pont, dans un contexte cloud déclaré à 262K tokens). Dans les deux cas, le pont retire les messages les plus anciens avant de dépasser sa limite et l'indique.

**Le bouton d'arrêt n'arrête pas tout de suite.** Il coupe l'affichage, mais la génération en cours se termine. Attends sa fin avant de passer en mode jeu.

**Le modèle peut se tromper avec assurance.** Pour une version, une commande sensible ou un chiffre, demande la source ou vérifie.

## Bien demander

Un modèle de cette taille répond mieux à une demande précise et courte.

- Donne le contexte utile en une ou deux phrases : ce que tu fais, ce que tu connais déjà.
- Pose une question à la fois.
- Pour un sujet long, demande d'abord un plan, puis chaque partie séparément.
- Pour une information qui a pu changer, écris « cherche sur le Web et donne tes sources ».

Exemple : « Je connais les services systemd. Explique-moi ce qu'un rôle Ansible apporte par rapport à un simple playbook, avec un petit exemple. »

## Obtenir un fichier

Demande le format explicitement : « Fournis une fiche en Markdown, PDF et DOCX » ou « Génère un `main.tf` commenté ». Des liens de téléchargement s'ajoutent à la réponse. Ils sont valables 24 heures : télécharge les fichiers pour les garder. Voir [Fichiers et schémas](06-fichiers-et-schemas.md).

## Interroger un projet depuis le chat

Le chat peut lire tes projets, **en lecture seule**. Des commandes, comprises par le programme (jamais par le modèle), choisissent le projet :

| Tu écris | Ce qui se passe |
|---|---|
| `!projets` | liste tes projets, avec leur état et leur cloud |
| `!projet daily` | sélectionne le projet (un morceau d'identifiant ou de titre suffit s'il est unique) |
| `!etat` | tâches, pause, cloud, modèle utilisé, traitement en cours |
| `!quitter` | n'utilise plus de projet |
| `!garder [titre]` | garde la dernière réponse du rôle comme **proposition** du projet |
| `!propositions` | liste les propositions (numéro, titre, état, origine) |
| `!voir 2` | affiche la proposition 2 |
| `!accepter 2` | demande l'acceptation : le pont donne une **phrase à taper** pour confirmer |
| `!refuser 2` | écarte la proposition 2 (elle reste consultable) |
| `!lancer`, `!pause`, `!reprendre` | exécute ou contrôle le plan approuvé en arrière-plan |
| `!pratique [tâche]` | affiche l'étape guidée qui attend ton travail |
| `!soumettre <tâche> <explication>` + fichiers | remet ton travail et lance le retour du spécialiste |
| `!auditer`, puis `!relire` | lance les deux contrôles indépendants aux états prévus |
| `!modifier <tâche> <raison>` | prépare une révision cohérente ; une phrase humaine confirme |
| `!livrer` | prépare la livraison finale ; une phrase humaine confirme |
| `!importer` | consomme le dossier local de secours du projet avant analyse |
| `!aide` | rappelle ces commandes |

Une fois un projet sélectionné, pose tes questions normalement : le rôle reçoit un résumé du projet, son plan, la liste de ses livrables et les passages de tes documents qui répondent à la question (la recherche locale doit avoir été actualisée dans l'atelier). Chaque réponse commence par `📁 Projet : <id>` : c'est ce qui rappelle le projet choisi d'un message à l'autre.

- Les commandes répondent tout de suite, **même quand une tâche tourne**. Une question au modèle, elle, attend la fin du traitement en cours.
- Les réponses du pont (liste, état) ne sont jamais envoyées au modèle.
- **Cloud** : avec le modèle « · cloud », le contexte d'un projet ne part que si ce projet a un [accord cloud valide](12-cloud.md). Sinon rien n'est envoyé et le pont le dit. Une fois qu'un fil a touché un projet, il garde cette règle même après `!quitter` : ouvre une nouvelle conversation pour une question sans rapport.
- Le préfixe `/` est aussi accepté pour ces cinq commandes, mais Open WebUI utilise `/` et `@` pour ses propres raccourcis : `!` est le plus sûr.
- Le chat et l'atelier pilotent désormais le **même moteur jusqu'à la livraison** : exécution, pratique guidée, audits, révisions et paquet final utilisent exactement les mêmes états, verrous et garde-fous.

### Garder un document écrit dans le chat

1. Demande le document au rôle (« écris le runbook de déploiement »).
2. `!garder Runbook de déploiement` : la réponse devient la **proposition** n° 1 du projet. Elle n'est pas encore acceptée.
3. `!voir 1` pour la relire, `!accepter 1` pour la valider. Le pont répond avec une phrase du type :

   ```
   approuver proposition K7Q2
   ```

4. Tape cette phrase **exactement, comme message à part**. Elle ne marche qu'une fois, pendant 15 minutes, si la proposition n'a pas changé, et seulement comme **dernier message** de la conversation. La proposition est alors ajoutée aux **notes** du projet.

Ce qu'il faut savoir :

- Le code est fabriqué par le pont, pas par le modèle, et la réponse qui le contient n'est **jamais** envoyée au modèle : un document ou une consigne cachée ne peut donc pas approuver à ta place. Après cinq codes faux, les codes en attente sont annulés.
- Une note acceptée est un **texte écrit par un modèle, non vérifié**. Ce n'est **pas un livrable** : elle n'entre pas dans le paquet final et n'est pas auditée. Les livrables passent toujours par une tâche et l'audit de l'atelier.
- Les rôles et le chat lisent les notes comme des données du projet, avec leur origine (local ou cloud).
- Tout cela s'écrit dans le dossier `context/chat/` du projet ; rien d'autre n'est modifié. Si une génération est en cours, le pont répond « occupé » et le code reste valable.

### Créer et cadrer un projet depuis le chat

Les mêmes étapes que dans l'[atelier](04-atelier-projets.md), avec les mêmes garde-fous : le chat appelle le même moteur.

| Tu écris | Ce qui se passe |
|---|---|
| (un message avec ta demande), puis `!creer Titre` | le pont montre ce qu'il va créer et une phrase à taper ; **la demande est ton message précédent** |
| `approuver creation K7Q2` | le projet est créé et sélectionné ; il reste **local** (aucun accord cloud) |
| `!analyser` | le chef d'opérations rédige une analyse **en arrière-plan** (quelques minutes) ; `!etat` donne l'avancement |
| `!valider` | montre le brouillon prêt et la phrase qui l'approuve |
| `approuver analyse K7Q2` | l'analyse est enregistrée ; s'il manque des informations, le projet attend tes réponses |
| `!questions`, puis `!repondre 1 ta réponse` | tu réponds aux précisions demandées (réponses de 1 500 caractères au plus) |
| `!planifier`, puis `!valider` | même chose pour le plan : tâches, rôles, sorties attendues, critères de vérification |
| `approuver plan K7Q2` | le plan est approuvé ; le projet est prêt à travailler |

Ce qu'il faut savoir :

- **Un brouillon n'approuve jamais rien.** Seule la phrase, fabriquée par le pont, le fait, et seulement si le brouillon n'a pas changé depuis la génération du code (empreinte). Même règles que pour les propositions : usage unique, 15 minutes, dernier message de la conversation.
- Les commandes `!creer`, `!analyser`, `!planifier`, `!questions` et `!repondre` viennent **toujours de ton dernier message**, jamais du modèle. Répondre à une précision est une action de ta part, sans phrase de confirmation.
- Pendant qu'un brouillon se rédige, le chat répond « occupé » aux questions normales ; `!etat` reste disponible. Si le service redémarre, `!etat` signale le brouillon interrompu : relance-le.
- Le texte du brouillon est affiché sans liens ni images, et le mot « approuver » y est coupé : copier une phrase écrite par un modèle ne sert à rien.
- Après approbation du plan, `!lancer` conduit les mêmes tâches que l'atelier. `!etat` reste disponible pendant un traitement ; `!pause` demande une pause coopérative ; les audits et la livraison sont des étapes séparées.
- Après `!creer`, ce fil a « touché » le nouveau projet : le modèle cloud n'y répond pas tant que ce projet n'a pas d'[accord cloud](12-cloud.md).

## Joindre des fichiers et parler

Avant l'analyse d'un projet sélectionné, joins un PDF, un document Office, une archive, du code ou
une image : le fichier original est copié depuis le stockage local d'Open WebUI puis passe par la
**même chaîne d'ingestion que l'atelier**. Le RAG intégré d'Open WebUI est désactivé pour cette
route afin de ne pas créer une seconde vérité documentaire.

Les sources deviennent immuables dès que l'analyse commence. Un upload tardif est refusé au lieu de
modifier silencieusement le projet ou son accord cloud. Si le navigateur ne transmet pas correctement
le fichier original, dépose-le dans
`/srv/openclaw-local/state/chat-import/inbox/<projet>/` puis tape `!importer`.

La dictée utilise Whisper **local** sur le CPU en int8 ; la lecture à voix haute utilise également
un service local. Le texte dicté est relu avant envoi et le mode appel mains libres reste désactivé.
Voir le [test de fumée](../SMOKE_TEST_WEBUI.md) pour mesurer la qualité et la latence réelles.

## Chat ou atelier ?

Le chat et l'atelier sont maintenant deux vues du même moteur. Le chat est pratique pour piloter
avec des commandes et converser ; le dashboard reste plus confortable pour visualiser l'état,
les tâches, les fichiers et les preuves. Aucune des deux interfaces n'a plus d'autorité que l'autre.

## Démarrer et arrêter

```bash
./menu.sh --action webui-status
./menu.sh --action webui-stop --apply
./menu.sh --action webui-start --apply
```

Tes conversations sont conservées dans `/srv/openclaw-local/state/webui` et entrent dans les [sauvegardes](09-entretenir.md).
