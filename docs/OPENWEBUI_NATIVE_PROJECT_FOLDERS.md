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

**Important :** créer un chat dans le dossier ne suffit pas, en l'état
actuel, à sélectionner automatiquement le contexte ClawFedora du projet.
Au début de ce fil, utiliser `!projet <id>` ou
**Classer cette conversation** après le premier message. Dans un
sous-dossier ClawFedora reconnu, l'action retrouve automatiquement
le bon identifiant du projet mais demande toujours une confirmation.
Le classement des discussions et la sélection du contexte sont
deux états distincts, même lorsque le dossier est commun.

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
- Créer un nouveau fil dans un dossier ; noter que le contexte nécessite
  encore `!projet` (ne pas déclarer de sélection automatique).
- Tester les parcours terminaux sans s'attendre à voir des sessions
  OpenClaw natives apparaître comme des conversations WebUI.

Conserver les résultats sous forme de preuves **privées**, sans exporter
les historiques, jetons, captures de pages personnelles ni documents Notion.

**Statut :** couche d'intégration implémentée, contrôle navigateur natif
Fedora **à effectuer**.
