# Streaming progressif des discussions natives — canary contrôlé

## Périmètre réel

Le nouvel écran **Discussions** peut maintenant utiliser le même transport SSE
OpenClaw sécurisé que le pont local existant, sans montrer le jeton d'opérateur
au navigateur. Les fragments de texte apparaissent progressivement dans le
fil **uniquement si le canary local a été activé**.

**Première tranche volontairement restreinte :**
- rôle : `chef-operations` (Mentor) ;
- projet du fil : **aucun**, pour ne pas contourner l'injection de contexte
  et les autorisations du moteur de projets ;
- question texte simple uniquement ; commandes, demandes `!continuer`,
  confirmations et autres rôles utilisent la route JSON stable ;
- moteur : Ollama + OpenClaw local, **sans fallback cloud**.

Sans activation explicite, l'interface conserve `/api/chat/send` et
la réponse complète historique. Le navigateur demande seulement à
`GET /api/chat/stream-capability` si le canary est disponible ; il ne peut
ni le créer, ni choisir un modèle, ni définir une URL de Gateway, ni obtenir
l'authentification interne.

## Protection contre une génération interrompue

Le service enregistre **avant** l'inférence une intention `pending` dans
le fichier privé de la discussion. Chaque fragment peut être affiché comme
prévisualisation provisoire, mais **aucun fragment n'est ajouté au transcript
définitif avant une terminaison OpenAI SSE valide (`finish_reason=stop`
puis `[DONE]`)**.

Après terminaison complète, le fichier est mis à jour de manière atomique et
le navigateur recharge la conversation canonique. En cas de coupure, erreur
Gateway, quota de taille ou navigation interrompue :

- la liaison SSE source est fermée ;
- la réponse partielle n'est pas enregistrée comme réponse accomplie ;
- `pending` reste présent afin d'imposer une vérification humaine avant
  tout nouvel envoi dans le fil ;
- aucune relance, annulation de tâche ou approbation n'est déclenchée par le
  modèle.

Le plafond de sortie est 64 000 octets. Le transcript natif conserve les
limites existantes de 850 Kio et 900 messages. L'interface utilise
`textContent`, pas du HTML provenant de la génération.

## Activation et retour arrière

Le raccordement **ne change pas la configuration du Gateway**.
L'activation canary privée est exactement celle décrite dans
[STREAMING_SSE_PREPARATION.md](STREAMING_SSE_PREPARATION.md) :

1. Préqualifier les versions OpenClaw/Ollama, les outils et les modèles
   locaux épinglés ; s'assurer que le Gateway reste lié à `127.0.0.1`.
2. Activer manuellement le marqueur privé `state/webui/native-sse.enabled`
   (mode 0600 et contenu exact `local-mentor-sse-v1`).
3. Appliquer le patch géré et redémarrer le Gateway et le service
   du tableau de bord sur Fedora, après sauvegarde et tests.
4. Tester d'abord un **nouveau fil Mentor sans projet** et une longue réponse,
   puis une interruption volontaire et la relecture du `pending`.
5. Pour revenir au mode nominal : supprimer le marqueur canary géré,
   réappliquer le patch qui désactive l'API HTTP d'opérateur et redémarrer
   les services. La route JSON stable reste inchangée.

Ne jamais committer un jeton Gateway ou activer manuellement une API
opérateur liée à une interface réseau non locale.

## Réception

- `tests/test_atelier_chat_stream.py` : route same-origin, role/projet,
  déconnexion, fragments et marqueur de reprise incertaine, validation
  de l'intégration à un faux pont HTTP SSE.
- Les CI ne prouvent pas la vitesse des tokens, le délai réel au premier
  fragment, l'effet d'une annulation côté modèle ou la compatibilité
  du Gateway OpenClaw installé sous Fedora 45.
- Ces mesures exigent un essai physique sur le Ryzen 7 7700 / Intel Arc B580
  avec le couple Qwen / Ornith réellement installé.

**Hors périmètre :** streaming des sept agents, des fils OpsDesk/BankFlow
et de leurs actions, streaming cloud, reprise automatique de flux interrompus,
réglages GPU et tableau de performances. Ces points demandent des
qualifications distinctes.
