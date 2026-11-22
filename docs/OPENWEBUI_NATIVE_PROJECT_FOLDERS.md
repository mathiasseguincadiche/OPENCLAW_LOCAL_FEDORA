# Projets ClawFedora dans la barre latérale native Open WebUI

[← Discuter](fiches/03-discuter.md) · [Moteur de projets](fiches/04-atelier-projets.md) · [Recette WebUI](SMOKE_TEST_WEBUI.md)

## Ce que l'intégration unifie

La **référence des projets** reste `/data/IA/Openclaw/projects/` :
identifiant, documents, tâches, livrables, état et preuves. Open WebUI
0.12.3 est un **client de chat** de ce même registre via le pont
`127.0.0.1:18891`, sans stockage concurrent des projets.

Après `./menu.sh --action webui-seal --apply` et la mise à jour normale
des services, une action gérée supplémentaire apparaît sous les messages :
**Afficher les projets dans le menu**.

1. Sur une réponse de la conversation, cliquer sur l'action.
2. Relire puis confirmer la création des dossiers de projet **dans
   la barre latérale native d'Open WebUI**.
3. L'action crée le dossier racine `Projets ClawFedora`, puis un
   sous-dossier par projet présent dans le registre local (maximum 50).
   Les sous-dossiers affichent le titre et l'identifiant canonique.
4. Actualiser la barre latérale ou la page si nécessaire. Les dossiers
   sont reconnus par des métadonnées gérées, pas seulement par leur nom.
5. Relancer l'action après création de nouveaux projets. L'opération
   est idempotente et **ne déplace, ne copie, ne supprime et ne renomme
   aucune conversation préexistante**.

On peut **démarrer un nouveau chat dans un dossier natif** et le retrouver
ultérieurement dans ce dossier via la navigation standard d'Open WebUI.
Le stockage et l'historique de ce chat restent la responsabilité d'Open WebUI
(`/data/IA/Openclaw/state/webui/data/webui.db`).

## Associer une conversation et son contexte

L'action **Classer cette conversation** fonctionne uniquement depuis
une conversation **enregistrée**, possédée par l'utilisateur administrateur
connecté.

1. Si le fil se trouve déjà dans un sous-dossier ClawFedora géré, l'action
   identifie le projet à partir des métadonnées du dossier appartenant au
   compte connecté. Sinon, l'utilisateur choisit le projet dans la liste.
2. L'action vérifie de nouveau que le projet existe, que le chat
   appartient à ce compte et que son message assistant est modifiable.
3. Elle demande un **accord explicite** pour déplacer **ce seul chat**,
   éventuellement depuis un ancien dossier.
4. Elle crée au besoin le dossier de projet, y range le chat et insère
   le marqueur de contexte `📁 Projet : <identifiant>` dans la dernière
   réponse de la conversation.
5. Le pont ClawFedora utilise ce marqueur sur les échanges ultérieurs
   pour lire le contexte autorisé de ce projet. Les fichiers du projet
   ne sont pas réécrits.

Si la confirmation est annulée, si l'utilisateur n'est pas administrateur,
si l'identifiant du chat est absent, si le projet a été supprimé ou si
le dossier est en conflit avec un dossier personnel : **refus**.

## Continuité automatique du contexte pour les chats enregistrés

Après la mise à jour du filtre géré par `webui-seal --apply`, une **conversation
déjà enregistrée** dans un sous-dossier natif ClawFedora peut récupérer
automatiquement **en lecture seule** le contexte de ce projet dès son prochain
message, sans taper `!projet` et sans nouveau clic de classement :

1. Le filtre Open WebUI actif consulte le chat **appartenant à l'admin connecté**,
   puis son dossier et la racine gérée par les API natives de la version épinglée.
2. Il signe un petit reçu de contexte (projet canonique, chat, propriétaire,
   horodatage et empreinte du dernier message) avec le secret du pont local.
3. Le pont vérifie la signature, l'expiration, la correspondance du message
   et l'existence du projet avant de charger son contexte.
4. Le prochain message de réponse porte le marqueur `📁 Projet : <id>`, ce qui
   permet de conserver cette sélection dans l'historique natif.

**Un fil nouvellement ouvert, mais pas encore enregistré**, ou un fil hors
dossier géré, conserve le fonctionnement antérieur : utiliser `!projet <id>`
ou **Classer cette conversation** après le premier message si nécessaire.
La création d'un simple dossier n'ouvre aucune session native OpenClaw.

Si un fil possède déjà un marqueur pointant vers un **autre projet** que son
dossier géré, le pont refuse la requête : il ne choisit pas silencieusement
entre deux contextes. Reclasser explicitement la conversation ou la déplacer
vers le bon dossier. Tant que le fil reste dans son dossier ClawFedora géré,
`!quitter` et `!projet autre-id` sont refusés ; il faut d'abord changer
son classement.

Le filtre ne signe **que les conversations enregistrées** dont l'utilisateur
et le dossier sont confirmés par les API natives. Les noms de dossiers,
messages du modèle et champs de requête non signés ne donnent aucun droit.
Une sélection par dossier **n'accorde ni consentement cloud, ni approbation
d'action, ni accès aux VM**, et n'importe **aucun historique de terminal**.
Les anciens projets cités dans le même fil continuent de compter dans les
contrôles de confidentialité cloud.

## Conversations terminal et WebUI : séparation volontaire

L'atelier partage les **projets persistants**, pas toutes les sessions
des interfaces.

- **Open WebUI** : historique natif dans sa base, rangé par dossiers.
- **Atelier Projets `:18890`** : lit le même registre de projets, avec
  sa propre sélection active pour l'interface graphique.
- **CLI ClawFedora** : opère sur les mêmes projets et décisions persistantes.
- **CLI / TUI native OpenClaw** : ses conversations ne deviennent **pas**
  automatiquement des chats WebUI. Aucun import/rejeu silencieux des
  messages, outils ou pièces jointes ; les sessions gardent leurs droits.

Une future importation de sessions doit être **explicite**, limitée à un
utilisateur et auditée (identité, ordonnancement des messages, secrets,
pièces jointes et provenances), sinon elle risquerait de produire
un historique faux ou de divulguer des contenus privés.

## Permissions et intégrité

- Fonctions réservées à l'utilisateur **admin** de l'instance personnelle.
- Les dossiers sont créés par les modèles natifs
  `open_webui.models.folders.Folders` de la version 0.12.3, dans
  **son propre** stockage. Pas de clé API supplémentaire ni SQL direct.
- Les actions contrôlent la propriété du fil avec
  `Chats.get_chat_by_id_and_user_id` avant tout changement de dossier ;
  seule la conversation sélectionnée peut être déplacée.
- Les dossiers personnels non marqués ClawFedora ne sont jamais adoptés
  ou remplacés. Une collision de nom ou des métadonnées incohérentes
  entraînent un refus, sans tentative de réparation destructive.
- Aucun push GitHub, écriture Notion, accès OpenRouter, changement de
  rôles ou approbation de projet n'est déclenché.
- Les nouveaux éléments de l'interface **ne donnent pas à l'IA** le
  droit d'exécuter du code, de choisir les projets ou de publier.

## Qualification

Les tests unitaires vérifient les créations idempotentes, l'absence de
déplacement automatique, la validation des identifiants, la propriété
des conversations et les confirmations strictes.

**La CI n'ouvre pas une vraie session administrateur native Open WebUI**.
Sur Fedora, après installation et scellement :

- Vérifier l'apparition des deux nouvelles actions.
- Créer deux projets fictifs ; synchroniser deux fois et vérifier
  l'absence de dossiers dupliqués.
- Démarrer un fil de test ; le classer dans l'un des dossiers ; rouvrir
  Open WebUI et vérifier l'historique et le marqueur sélectionné.
- Vérifier que l'ancien dossier d'un autre fil ne change pas.
- Annuler le classement et vérifier qu'aucun déplacement n'a lieu.
- Après enregistrement d'un fil dans un dossier géré, envoyer un nouveau
  message et vérifier la sélection automatique et le bon contenu de projet.
- Confirmer que le **tout premier message d'un fil non encore enregistré**
  garde le parcours manuel `!projet` ou « Classer cette conversation ».
- Déplacer un fil déjà marqué dans un autre dossier géré : contrôler le
  **refus du conflit**, sans écriture, exécution ni appel au cloud.
- Essayer un dossier personnel homonyme, un chat d'un autre propriétaire,
  un reçu expiré, une signature falsifiée et un projet supprimé : aucun
  chargement de contexte ne doit être autorisé.
- Vérifier le garde-fou cloud avec un projet privé et les éventuelles
  références précédentes à d'autres projets dans le même fil.
- Tester les parcours terminaux sans s'attendre à voir des sessions
  OpenClaw natives apparaître comme des conversations WebUI.

Conserver les résultats sous forme de preuves **privées**, sans exporter
les historiques, jetons, captures de pages personnelles ni documents Notion.

**Statut :** continuité de contexte implémentée pour les chats gérés et
enregistrés, sous réserve de l'exécution des tests automatisés et de la
recette navigateur Open WebUI native sur Fedora. La CI simulée ne remplace
pas cette recette.
