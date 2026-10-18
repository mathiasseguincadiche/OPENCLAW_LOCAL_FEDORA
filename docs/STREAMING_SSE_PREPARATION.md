# Streaming SSE natif OpenClaw → Open WebUI : raccordement canary sécurisé

[← Programme](PROGRAMME_AMELIORATION_2026.md) · [Test WebUI](SMOKE_TEST_WEBUI.md) · [Architecture](fiches/11-comment-ca-marche.md)

## Situation exacte

L'API Chat Completions native d'OpenClaw 2026.9.8 accepte le streaming
`text/event-stream`. **Mais ce point d'entrée dispose de privilèges
d'opérateur**, y compris sous authentification par jeton. Il ne doit
**jamais** être exposé directement au navigateur, à Open WebUI, aux sept
agents ou à une machine distante.

Le module `src/clawfedora/stream_transport.py` décode les événements
SSE du Gateway. Le raccordement de production est désormais proposé par
`src/clawfedora/native_stream.py` et `webui_bridge.py`, **uniquement en
activation canary privée**. L'installation normale conserve la réponse
CLI en un bloc. Les discussions cloud, commandes de projet, pièces jointes
et rôles autres que le Mentor local restent sur leur chemin habituel.

Avant **toute** connexion SSE, le pont réutilise le runner OpenClaw en mode
prévalidation seule : version OpenClaw et Ollama exactes, empreinte du modèle
Qwen, configuration des sept agents, interdictions des outils dangereux et
absence de repli automatique. Le Gateway ne reçoit jamais le jeton du pont
Open WebUI. Le jeton d'opérateur existant est lu depuis le fichier privé de
configuration OpenClaw, jamais depuis une réponse du modèle.

## Propriétés techniques apportées

- Connexion uniquement vers `127.0.0.1:18789` et
  `POST /v1/chat/completions`. Pas d'URL utilisateur, de proxy arbitraire
  ou de téléchargement réseau non prévu.
- Cible `openclaw/<agent-id>` validée parmi les sept rôles connus ;
  identifiant de session borné, message texte borné et opérateur
  exclusivement côté serveur.
- Aucun champ `tools`, `x-openclaw-model` ou fournisseur cloud transmis.
- Décodage SSE **fragment par fragment après terminaison de chaque événement** :
  les lignes `data:` incomplètes ne sont jamais affichées, les rôles autres
  qu’`assistant`, les structures d'outils, les doublons de fin et les
  erreurs sont refusés. Un éventuel événement de consommation finale sans
  texte est toléré uniquement après `finish_reason=stop` ; `[DONE]` reste
  obligatoire.
- Limites de volume par événement (128 Kio) et sortie (64 000 octets).
- Fermeture de la connexion réseau lors de l'abandon par le consommateur.
- Tests hors ligne : premier fragment avant le suivant, erreurs réseau,
  troncature de ligne et d'événement, rôle usurpé, doublon de terminaison,
  plafonds, fermeture et liaison du **faux Gateway** au vrai pont HTTP
  Open WebUI sans divulgation du jeton opérateur.

## Conditions de qualification et d'activation

1. **Réutiliser les vérifications de `openclaw_runner`** : versions
   OpenClaw/Ollama épinglées, intégrité Qwen sur Intel Arc, roster exact
   des sept rôles, outils interdits et absence de repli automatique
   vers un autre fournisseur. Ne jamais contourner cette étape.
2. **Garder le verrou partagé du worker pendant toute la génération**,
   y compris quand Open WebUI coupe la connexion. Tout résultat
   interrompu doit rester `FAILED/INCOMPLETE`, jamais `PASS`.
3. **Conserver la préparation existante des prompts et documents** :
   contexte, pièces jointes, accord cloud par projet, filtre des secrets,
   journaux et liens produits. Aucun contenu sensible ne doit suivre
   une nouvelle route vers DeepSeek par inadvertance.
4. **Lire le jeton du Gateway depuis sa configuration privée** (0600), sans
   jamais l'insérer dans Open WebUI ou une réponse ; garantir que le
   service écoute en boucle locale et que les mécanismes de provisionnement
   n'exposent pas la valeur.
5. **Limiter d'abord au chat Qwen purement local**, sans pièces jointes
   ni projets, puis qualifier les autres cas une fois les barrières
   vérifiées. La route DeepSeek nécessite en plus la validation de
   la passerelle, du budget et de l'éventuel échec partiel.
6. **Ajouter au pont OpenAI-compatible une émission SSE réellement
   incrémentale** : envoi de fragments au navigateur au fil de l'eau,
   terminaison `finish_reason=stop` seulement après succès,
   erreur visible sinon, aucune injection de faux marqueur projet.
7. Valider la version OpenClaw épinglée et l'instance Open WebUI actuellement
   épinglée en canary ; la migration v0.12 reste une qualification séparée.
   Réaliser ensuite les essais finaux sur Fedora.

Le code livré n'active pas automatiquement l'API opérateur : le marqueur
0600, le patch géré et le redémarrage du Gateway constituent une activation
manuelle explicite. La qualification réelle reste à réaliser.


## Activation canary sur Fedora (manuelle, après CI verte)

Le code préparé dans le dépôt ne modifie ni la configuration ni les services
réels tant que l'utilisateur n'active pas le mode canary. **Ne pas confondre
CI verte, API configurée et streaming confirmé dans le navigateur.**

1. Conserver une sauvegarde de l'état OpenClaw et les résultats d'un
   `./menu.sh --action health` propre. Vérifier que
   `state/openclaw/openclaw.json` est un fichier ordinaire privé **0600**
   contenant un `gateway` de mode `local`, avec `bind=loopback`,
   `gateway.auth.mode=token` et un jeton d'opérateur existant d'au moins
   32 caractères. Une référence d'environnement ne peut être utilisée que
   via `OPENCLAW_GATEWAY_TOKEN` disponible **uniquement côté serveur**.
   En l'absence de ce jeton, l'activation échoue : ne pas en générer un
   différent du secret réellement configuré dans le Gateway.
2. Créer le marqueur privé depuis la session propriétaire du runtime,
   sans écraser un fichier non géré. Exemple à adapter au chemin réel du
   runtime ; ne pas le placer dans Git :

   ```bash
   RUNTIME_ROOT="/IA/Openclaw"
   # Adapter RUNTIME_ROOT si l'installation utilise le chemin utilisateur.
   install -m 0600 /dev/null "$RUNTIME_ROOT/state/webui/native-sse.enabled"
   printf 'local-mentor-sse-v1\n' > "$RUNTIME_ROOT/state/webui/native-sse.enabled"
   chmod 0600 "$RUNTIME_ROOT/state/webui/native-sse.enabled"
   ```

3. Revalider et appliquer la configuration épinglée, puis redémarrer les
   deux services locaux :

   ```bash
   bash scripts/linux/03_configure_openclaw.sh --apply
   systemctl --user restart openclaw-gateway.service
   systemctl --user restart clawfedora-webui-bridge.service
   ```

   Le patch géré ajoute alors **uniquement**
   `gateway.http.endpoints.chatCompletions.enabled=true`, tout en conservant
   `bind=loopback`. Si le mode/token n'est pas conforme, le pont refuse
   **avant** l'appel HTTP. Aucun jeton n'est renvoyé au navigateur.

4. Depuis Open WebUI, choisir **Mentor infrastructure/OPS · local** et
   une nouvelle discussion sans projet ni fichier. Envoyer une longue
   question DevOps : vérifier le premier fragment avant le dernier, la
   fermeture au bouton Annuler, l'absence de requête vers le cloud, le
   verrou du worker et l'absence de texte de réponse complète en cas de
   terminaison interrompue. Refaire les tests de refus (outil, commande,
   projet, fichier, changement de modèle) du smoke test.

### Retour arrière / restauration nominale

Supprimer **uniquement** le marqueur créé manuellement, puis réappliquer
le patch validé et redémarrer le Gateway et le pont :

```bash
rm -- "$RUNTIME_ROOT/state/webui/native-sse.enabled"
bash scripts/linux/03_configure_openclaw.sh --apply
systemctl --user restart openclaw-gateway.service
systemctl --user restart clawfedora-webui-bridge.service
```

Le patch nominal réapplique explicitement `enabled=false` afin de
fermer l'API opérateur même lorsque le gestionnaire de patch fusionne
les réglages au lieu de supprimer les champs absents.
Aucune modification du jeton cloud OpenRouter n'est nécessaire.

**Limites de preuve :** les tests CI vérifient le raccordement à un Gateway
simulé et les refus avant connexion ; ils ne prouvent pas le comportement
d'une instance OpenClaw épinglée ni les flux de son fournisseur réel sur
Intel Arc B580. Ces essais ont lieu en dernier sur le Fedora natif.

**Documentation officielle :**
https://docs.openclaw.ai/gateway/openai-http-api

## Réception finale

Comparer les horodatages du premier et du dernier fragment pour une
réponse de plusieurs paragraphes ; annuler pendant l'inférence et
vérifier l'arrêt effectif sans fuite du verrou ni coût masqué.
Rejouer les tests de route cloud privée, l'historique, les erreurs
fournisseur, l'attachement de fichiers et les approbations.
Faire les essais **sur Fedora natif**, sans VM Rocky ni changement de
l'architecture IA.
