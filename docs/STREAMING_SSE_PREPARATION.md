# Streaming SSE OpenClaw → Open WebUI : couche de transport préparée

[← Programme](PROGRAMME_AMELIORATION_2026.md) · [Test WebUI](SMOKE_TEST_WEBUI.md) · [Architecture](fiches/11-comment-ca-marche.md)

## Situation exacte

L'API Chat Completions native d'OpenClaw 2026.9.8 accepte le streaming
`text/event-stream`. **Mais ce point d'entrée dispose de privilèges
d'opérateur**, y compris sous authentification par jeton. Il ne doit
**jamais** être exposé directement au navigateur, à Open WebUI, aux sept
agents ou à une machine distante.

Le code `src/clawfedora/stream_transport.py` est une **première couche
de transport serveur à serveur**, préparée et testable sans matériel.
Elle sait décoder **progressivement** les fragments de texte SSE d'OpenClaw,
refuser les flux partiels ou erronés et demander l'arrêt de la source
lorsqu'un consommateur ferme le générateur.

**Même après ce durcissement**, le pont HTTP Open WebUI continue d'utiliser la voie CLI
en attente de réponse complète.** Ne pas présenter ce nouveau module
comme un streaming déjà visible dans le navigateur.

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

## Conditions indispensables avant activation dans le pont

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
4. **Stocker le jeton de Gateway séparément**, en 0600 hors Git, sans
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
7. Valider la version OpenClaw épinglée et l'instance Open WebUI 0.12
   en canary, puis seulement effectuer les essais sur Fedora.

L'étape de source de flux ne constitue pas à elle seule l'activation
de la fonctionnalité. **Ne pas changer la configuration du Gateway pour
activer une API opérateur tant que les garanties ci-dessus ne sont pas
couvertes par des tests de régression.**

## Réception finale

Comparer les horodatages du premier et du dernier fragment pour une
réponse de plusieurs paragraphes ; annuler pendant l'inférence et
vérifier l'arrêt effectif sans fuite du verrou ni coût masqué.
Rejouer les tests de route cloud privée, l'historique, les erreurs
fournisseur, l'attachement de fichiers et les approbations.
Faire les essais **sur Fedora natif**, sans VM Rocky ni changement de
l'architecture IA.
