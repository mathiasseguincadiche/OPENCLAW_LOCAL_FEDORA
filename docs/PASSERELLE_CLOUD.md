# Passerelle cloud locale : conception et faits vérifiés

**Statut : la fondation (lot 3) et l'exécuteur multi-modèles (lot 4) sont en place. La passerelle elle-même, le filtre de confidentialité et le contrôle du budget ne sont pas encore écrits : le cloud ne peut donc pas être activé.**

Ce document complète `docs/PLAN_MIGRATION_HYBRIDE.md` (lot 1). Il fixe le contrat que les lots suivants doivent respecter et consigne ce qui a été **vérifié avec le vrai OpenClaw 2026.9.8** (`make native-cloud`, `make native-schema`, `make native-prompt`).

## Principe

OpenClaw ne parle jamais à OpenRouter. Il parle à une passerelle en boucle locale (`127.0.0.1:18892`, `config/core/cloud_policy.yaml`), qui seule lira la clé du fournisseur, filtrera tout le contenu sortant, réservera et comptera chaque appel facturé, puis transmettra à OpenRouter.

```
OpenClaw ──► fournisseur "cloudgw" (127.0.0.1:18892/v1) ──► [filtre + budget] ──► OpenRouter
```

## Faits vérifiés

| Question | Constat |
|---|---|
| OpenClaw accepte-t-il un fournisseur personnalisé à URL locale ? | Oui. `models.providers.cloudgw`, `api: openai-completions`, modèles déclarés statiquement, `models.mode: replace` : aucune découverte de catalogue, donc aucun accès réseau au démarrage. |
| Peut-on choisir le modèle par requête ? | Oui : `openclaw agent --model cloudgw/z-ai/glm-5.3-flash`. Les sept rôles gardent Qwen comme modèle principal ; le cloud se choisit à chaque tour. |
| Qui voit quoi ? | La passerelle reçoit le prompt système, l'historique et, au second appel d'une boucle d'outil, **les résultats d'outils**. Un tour avec un outil fait **deux appels facturables**. |
| Quel jeton circule ? | Un jeton **local** (`Authorization: Bearer <jeton local>`), lu dans la variable `CLAWFEDORA_CLOUD_GATEWAY_TOKEN`. La clé du fournisseur n'atteint jamais OpenClaw : le contrôle fait échouer toute fuite. |
| Usage en streaming ? | OpenClaw envoie `stream: true` et `stream_options.include_usage: true` ; l'usage et le coût peuvent donc être lus dans le dernier fragment. |
| Peut-on limiter le raisonnement avec `--thinking` ? | **Non** pour un fournisseur personnalisé (`low` refusé, seuls `off` et `ultra` sont acceptés). La limite sera donc **imposée par la passerelle**, qui injecte `reasoning` dans chaque requête (`upstream_params`). |
| Que se passe-t-il si le jeton manque ? | OpenClaw résout les secrets de **tous** les fournisseurs avant un tour : un jeton absent fait échouer **même un tour local**. L'environnement d'exécution doit donc toujours définir ce jeton dès que le fournisseur est configuré (lot 4). Avec le jeton défini et la passerelle arrêtée, les rôles locaux fonctionnent (`make native-prompt`). |
| Retour arrière | Désactiver le cloud supprime le fournisseur `cloudgw` d'une installation existante (migration vérifiée par `make native-schema`). |
| Quels modèles `--model` peut-il choisir ? | Seulement ceux de `agents.defaults.modelPolicy.allow` : Qwen, et le modèle cloud uniquement si le cloud est activé. |

## Exécuteur (lot 4)

`openclaw_runner(...)(role, prompt, session)` garde son comportement local. Un appelant qui a décidé d'utiliser le cloud passe `route="cloud"` ; rien ne bascule jamais seul du local vers le cloud.

- **Refus avant tout processus** : la route cloud exige un enregistrement d'activation (`state/cloud/activation.json`) prouvant que **chaque** contrôle requis par la politique (`privacy_filter`, `budget_guard`) est vérifié. Un seul contrôle vérifié ne suffit pas. Seule la future commande d'activation (lot 6) écrit cet enregistrement ; `revoke_activation` éteint le cloud.
- **Pas d'Ollama sur la route cloud** : ni version, ni inventaire, ni verrou de digest. Le tour passe par `openclaw agent --model cloudgw/z-ai/glm-5.3-flash` via la Gateway OpenClaw.
- **Configuration revérifiée** avant un tour cloud (avec le vrai CLI) : l'URL du fournisseur doit être exactement celle de la politique, le transport, le modèle déclaré, la liste d'autorisation, et la clé doit être une **référence d'environnement** (jamais une chaîne). `config get` masque le nom de la référence (`__OPENCLAW_REDACTED__`) mais garde sa forme : c'est cette forme qui est contrôlée.
- **Identité du modèle** : le tour échoue si le fournisseur ou le modèle réellement servis diffèrent. `state/model-runs/<session>.json` conserve route, fournisseur, modèle et tokens, **sans contenu**.
- **Jeton local** : `state/cloud/gateway.token` (droits 0600, répertoire 0700, créé une fois). L'environnement d'exécution le définit toujours (voir plus haut pourquoi). Hors d'un runtime géré, rien n'est écrit.
- **Réparation JSON** : écart assumé par rapport au plan initial (« sur la même route »). Une syntaxe JSON invalide renvoyée par le cloud est réparée **par le modèle local**, qui ne fait sortir aucune donnée et ne coûte rien. Si Ollama est indisponible, la tâche échoue (« relancer la tâche ») : un second appel cloud facturé n'a jamais lieu pour réparer.

Vérifié avec le vrai OpenClaw 2026.9.8 par `make native-cloud` : une vraie Gateway est démarrée, la route cloud est d'abord refusée, puis acceptée après activation ; la passerelle factice voit le jeton local, deux appels pour un tour avec un outil, et l'identité est enregistrée.

## Contrats imposés par `clawfedora validate`

- Cloud désactivé par défaut (`enabled_by_default: false`) ; l'activation est une décision d'exécution, hors dépôt.
- Aucun repli du local vers le cloud ni vers un modèle caché. Le repli cloud vers local est possible, mais visible.
- Confidentialité **et** budget sont tous deux requis (`requires`).
- Passerelle sur `127.0.0.1`, port valide non utilisé, jeton nommé par variable d'environnement, fichier de clé relatif à l'état d'exécution.
- Contexte et sortie du modèle cloud égaux aux limites quotidiennes (une seule source).
- `data_collection: deny` et `require_parameters: true` imposés ; tarifs de référence présents.
- Le modèle cloud est déclaré au catalogue, optionnel, et chaque rôle pointe vers lui.

## Reste à faire (lots suivants)

| Lot | Contenu |
|---|---|
| 5 | La passerelle et le filtre sur **tout** le corps de requête ; modes Apprendre et Travail |
| 6 | Réservation et journal de **tous** les appels (y compris interrompus), plafond de 25 € réels, commande d'activation avec auto-contrôles |
| 7 | Atelier : accord explicite par projet, pause visible |

## Ce que ce lot ne prouve pas

Aucun appel réel vers OpenRouter, aucun comportement de GLM, aucun essai sur le PC Fedora. Les tests utilisent une passerelle factice.
