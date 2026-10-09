# Discuter

[← Guide](../GUIDE.md)

Open WebUI est l'interface de discussion, à l'adresse `http://127.0.0.1:3000`. Elle sert aux questions de tous les jours, comme tu le ferais avec Claude ou ChatGPT.

## Choisir à qui tu parles

Le sélecteur de modèle en haut de la page liste les sept rôles. Tous utilisent le même Qwen : choisir un rôle change les consignes et les outils, pas le modèle. Si tu as activé le cloud, chaque rôle apparaît aussi en « · cloud (GLM) » : voir plus bas.

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
| « … · cloud (GLM) » | **Apprendre** : GLM-5.3 Flash par OpenRouter | des questions publiques, sans secret |

Le choix par défaut reste local. Une réponse cloud porte un bandeau « ☁️ Réponse du modèle cloud ». Si le filtre détecte un secret dans ton message, l'historique ou un résultat d'outil, rien ne part : la conversation passe en local (« 🔒 Conversation passée en local ») et le reste du fil y reste. Si le plafond de 25 € est atteint ou si le fournisseur est indisponible, la réponse vient du local avec un bandeau « 💻 ».

Le filtre arrête les secrets, pas un contenu confidentiel qui n'en a pas l'allure : en cas de doute, choisis « local ».

## Ce qu'il faut savoir

**La réponse arrive d'un bloc.** Open WebUI attend la fin de la génération avant d'afficher. Une réponse longue peut demander une à plusieurs minutes selon la vitesse mesurée au [premier essai](02-premier-essai.md).

**Une seule génération à la fois.** Si l'atelier Projets travaille, le chat répond qu'il est occupé, et inversement. Le modèle n'est jamais lancé deux fois en parallèle.

**La mémoire de la conversation est limitée.** Le chat transmet au modèle les messages les plus récents, jusqu'à 32 000 octets (environ 5 000 mots). Au-delà, les plus anciens ne sont plus transmis et le chat l'indique en tête de réponse. Si un détail ancien compte, rappelle-le.

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

## Chat ou atelier ?

Le chat explique et oriente. Il ne modifie jamais un projet de l'atelier, et les fichiers joints à une conversation ne deviennent pas des sources de projet. Pour un travail avec des documents, plusieurs étapes et des livrables relus, utilise l'[atelier Projets](04-atelier-projets.md).

## Démarrer et arrêter

```bash
./menu.sh --action webui-status
./menu.sh --action webui-stop --apply
./menu.sh --action webui-start --apply
```

Tes conversations sont conservées dans `/srv/openclaw-local/state/webui` et entrent dans les [sauvegardes](09-entretenir.md).
