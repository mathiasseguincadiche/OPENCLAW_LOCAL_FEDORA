# ClawFedora Local — plugin LM Studio expérimental

**Statut : prototype privé à qualifier sur Fedora.** Le code ne publie
rien sur LM Studio Hub et ne donne aucune permission GitHub/Notion
supplémentaire au modèle.

- **Generator** : envoie uniquement des échanges texte à
  `http://127.0.0.1:18894/v1/chat/completions` (pont indépendant).
- **Configuration par chat** : identifiant de projet explicite et
  sélection des sept agents OpenClaw.
- **Commandes humaines** : `!projets`, `!etat`, `!sources`,
  `!analyser`, `!planifier`, `!lancer`, `!auditer`, etc.
- **Approbations** : texte à usage unique envoyé par une personne en
  nouveau message ; aucun tool calling autonome.
- **Protection** : contexte inter-projets contradictoire refusé ;
  jeton privé 0600 lu dans `state/lmstudio/bridge.token` ;
  données et secrets non inscrits dans les logs du plugin.
- **Défaut** : pas de sélection automatique par nom de dossier natif,
  pas de copier-coller d'historique WebUI, pas d'images ou de RAG LM
  Studio, pas de cloud direct ni de publication.

Ce plugin est un **générateur dans le sélecteur de modèles LM Studio**,
et non un modèle d'inférence qui exécute ses propres tokens. OpenClaw
continue de piloter l'inférence Ollama existante.

**Installation, commandes et critères de réception :**
[LM Studio comme interface principale](../../docs/LMSTUDIO_PRIMARY_INTERFACE.md).

**Tests hors application :** `npm test` utilise seulement Node et la
bibliothèque standard. Installer la dépendance épinglée via `npm install`
avant `lms dev` ; la réussite de ces tests ne vaut pas validation du
SDK de la version LM Studio installée.
