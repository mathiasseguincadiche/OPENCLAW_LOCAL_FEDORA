# LM Studio comme interface principale — intégration pilote ClawFedora

> **Phase de migration réversible.** Ce document décrit le fonctionnement prévu
> et les points réellement vérifiables. Une PR verte ne valide pas à elle seule
> LM Studio, le pilote Intel Arc B580, les chats ni les permissions sur Fedora.

## Décisions d'architecture

| Besoin | Composant retenu | Contrat |
| --- | --- | --- |
| Conversations et dossiers | LM Studio natif | Historique enregistré par LM Studio ; classement manuel en dossiers |
| Projet attaché au chat | Config de plugin par conversation | Identifiant explicite, validé par le pont ; changement de projet = nouveau fil |
| Sept agents | Config de plugin par conversation | IDs canoniques issus de \`config/core/agents.yaml\` ; réponse via OpenClaw |
| Travail et état | Pont + Atelier Projets | Même moteur et verrou local ; pas de base de tâches parallèle |
| GitHub/Notion | Sources importées et révisions approuvées | Recherche locale ; ne pas activer le MCP tiers qui contourne les politiques |
| Actions | Messages de **l'utilisateur** \`!commande\` | Commandes traitées côté pont, jamais un appel d'outil généré par un LLM |
| Validations | Phrase de confirmation à usage unique | Nouvelle saisie humaine dans le chat ; annulation / expiration maintenues |
| Cloud | Désactivé dans le plugin pilote | Aucun appel direct à un fournisseur externe |
| Modèle local | OpenClaw → Ollama existant | LM Studio sert d'interface ; inférence LM Studio évaluée séparément |
| Retour arrière | Open WebUI non désinstallé | Les services et données WebUI restent indépendants |

La sélection d'un projet par le champ du plugin **n'expose pas** les dossiers
natifs LM Studio à ClawFedora. Le titre d'un dossier est cosmétique. Aucun
accès non documenté à la base de conversations LM Studio n'est utilisé.

## Préparer le pont sur Fedora 45

Le socle OpenClaw, le worker, le venv Python et l'atelier doivent déjà être
installés sur \`/data/IA/Openclaw\` ; le contrôle matériel de Fedora 45 et
SELinux Enforcing reste requis. L'application LM Studio elle-même est installée
séparément selon sa documentation officielle. Ne pas la déclarer compatible
avec le GPU B580 sans essai sur la machine.

Dans le dépôt ClawFedora à jour :

~~~bash
./menu.sh --action lmstudio-install             # prévisualisation sans effet
./menu.sh --action lmstudio-install --apply     # crée l'unité et le jeton
./menu.sh --action lmstudio-status              # doit afficher ACTIVE
~~~

L'installation prépare **uniquement** :

- l'unité utilisateur \`clawfedora-lmstudio-bridge.service\` ;
- le jeton propriétaire 0600 dans \`/data/IA/Openclaw/state/lmstudio/bridge.token\` ;
- le pont OpenAI-compatible authentifié \`http://127.0.0.1:18894/v1\`
  (boucle locale, service distinct du pont WebUI \`:18891\`).

Elle n'exécute **aucun** \`npm install\`, téléchargement LM Studio,
modification de la configuration GPU, service cloud ni arrêt d'Open WebUI.
Elle ne publie jamais le jeton.

Pour stopper ce pont sans effacer de données :

~~~bash
./menu.sh --action lmstudio-stop --apply
./menu.sh --action lmstudio-start --apply
~~~

## Brancher le plugin local dans LM Studio

Le code du plugin se trouve dans
[\`plugins/lmstudio-clawfedora\`](../plugins/lmstudio-clawfedora).
Ce générateur LM Studio ne demande pas de clé OpenRouter ou de token à coller
dans un formulaire ; il lit le jeton 0600 appartenant au compte courant.

1. Installer une version LM Studio disposant du SDK Plugins et du mode
   développeur. L'API de plugins est encore une surface d'intégration à
   **qualifier sur la version installée**.
2. Dans le dossier du plugin, installer la dépendance épinglée
   \`@lmstudio/sdk@1.4.0\` avec npm. Ce dépôt fournit le code source du
   prototype ; aucune compatibilité runtime n'est déclarée sans essai.
3. Lancer \`lms dev\` depuis ce dossier, sélectionner le générateur
   **clawfedora-local** dans la liste des modèles de LM Studio.
4. Dans les **paramètres du plugin de cette conversation** :
   - **Projet ClawFedora** : identifiant exact donné par \`!projets\`
     (\`opsdesk\` uniquement si c'est le vrai identifiant local) ;
   - **Agent OpenClaw** : choisir parmi les sept rôles ;
   - si aucun projet n'est choisi, poser \`!projets\` dans un chat sans projet.
5. Ranger manuellement les chats dans les dossiers natifs LM Studio. Le
   choix du dossier **n'accorde pas** le contexte ClawFedora : le champ
   explicite reste la seule source.

Commandes de développement, une seule fois après avoir vérifié les
dépendances et la version de LM Studio :

~~~bash
cd /data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA/plugins/lmstudio-clawfedora
npm install                 # télécharge uniquement les dépendances du plugin
npm test                    # contrat local, sans jeton ni génération
lms dev                     # mode développeur, à arrêter après l'essai
~~~

Ne pas publier ce plugin sur le Hub, ni exposer l'API locale sur le réseau.
Ne pas copier le jeton dans \`mcp.json\`, Notion ou GitHub.

## Usage pratique

- Liste des projets : dans un nouveau chat sans projet, écrire \`!projets\`.
- Discussion : choisir \`projectId\` et \`agentRole\`, puis poser la question
  normalement ; le pont lit le projet et les sources approuvées en local.
- État et sources : \`!etat\`, \`!sources\` ; analyse et plan :
  \`!analyser\`, \`!planifier\`, \`!questions\`.
- Travail : \`!lancer\`, \`!pause\`, \`!reprendre\`, \`!pratique\`,
  \`!auditer\`, \`!relire\`, \`!livrer\`, selon l'état.
- Décisions : les confirmations apparaissent **dans la réponse du pont**.
  Pour confirmer, envoyer soi-même la phrase exacte demandée en tant que
  **nouveau message utilisateur isolé**. Une proposition du modèle ne
  constitue jamais cette validation.
- Dossier Atelier : \`http://127.0.0.1:18890\` affiche les tâches,
  dépendances, journaux, imports, et validations détaillées.

Attention : la conversation et les commandes utilisent le **même moteur**
que l'ancienne passerelle. Si le projet n'existe pas, son contexte est
refusé. Si un chat a déjà consulté un autre projet, **ouvrir un nouveau
fil** : aucune requalification silencieuse, même si l'on renomme son dossier.

Les pièces jointes sont à importer dans l'Atelier Projets. L'export ou
l'import historique des conversations WebUI **n'est pas réalisé** par cette
version du plugin. Les actions sont disponibles comme commandes humaines
textuelles, **pas encore comme boutons natifs LM Studio**.

## Recette de remplacement : critères à obtenir AVANT la suppression WebUI

- [ ] LM Studio démarre et utilise le plugin sur la session GNOME 51,
      avec l'appareil réel et l'Intel Arc B580.
- [ ] Sept rôles testés : un chat local par rôle, résultat attribuable à
      OpenClaw, sans changement indu de rôle.
- [ ] Deux projets de test, deux chats distincts : aucune donnée de l'un
      ne fuit vers l'autre ; changement de champ en cours de fil refusé.
- [ ] Recherche GitHub et Notion privée dans un projet autorisé ; ancien
      commit obsolète non présenté comme courant.
- [ ] Commandes de lecture, analyse, planification, préparation,
      exécution et audit réellement exercées sur un projet jetable.
- [ ] Refus des actions incompatibles, des confirmations expirées et
      de phrases injectées par le modèle ; une approbation humaine
      explicite et séparée requise.
- [ ] Annulation et fermeture de LM Studio : constater ce qu'une
      demande déjà acceptée a fait côté pont (annuler la génération
      ne défait pas une commande déjà exécutée).
- [ ] Export d'un chat LM Studio, redémarrage et conservation de
      l'historique ; absence de migration implicite des anciens chats.
- [ ] Adaptation de l'interface aux écrans mobiles : LM Studio est une
      application locale, **pas** un clone du site Open WebUI.
- [ ] Sauvegarde/restauration des conversations LM Studio : testée,
      documentée, chiffrée selon la politique de sauvegarde.
- [ ] Comparaison qualitative LM Studio vs WebUI sur les mêmes
      questions, temps de réponse et tâches (en tenant compte du
      modèle d'inférence qui reste initialement identique).
- [ ] Contrat GitHub CI vert, puis recette réelle Fedora signée ;
      seulement ensuite retirer le conteneur, ses services et ses
      migrations, sans perdre de données.

**À ne pas annoncer prématurément :** tests de LM Studio réels, isolation
des chats prouvée sur Fedora, synchronisation automatique des dossiers,
boutons d'action natifs, migration de l'historique WebUI ou performance
GPU supérieure. La CI ne mesure aucune de ces affirmations.

## Documentation technique officielle

- [LM Studio — Plugins](https://lmstudio.ai/docs/typescript/plugins)
- [LM Studio — Generators](https://lmstudio.ai/docs/typescript/plugins/generator)
- [LM Studio — Configurations par chat](https://lmstudio.ai/docs/typescript/plugins/custom-configuration)
- [LM Studio — OpenClaw](https://lmstudio.ai/docs/integrations/openclaw)
