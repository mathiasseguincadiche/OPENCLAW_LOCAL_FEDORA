# Réglages

[← Guide](../GUIDE.md)

## Les valeurs en place

| Réglage | Valeur | Fichier |
|---|---|---|
| Modèle | Qwen 3.5 9B, quantification Q4_K_M, environ 6,6 Go | `config/model_catalog.yaml` |
| Contexte | 32 768 tokens | `config/core/openclaw_policy.yaml` |
| Longueur maximale d'une réponse | 4 096 tokens | `config/core/openclaw_policy.yaml` |
| Historique transmis par le chat | 32 000 octets | `config/webui_policy.yaml` |
| Générations simultanées | une seule | service Ollama et verrou de l'atelier |
| Déchargement du modèle | après 3 minutes d'inactivité | `config/core/openclaw_policy.yaml` |
| Raisonnement long (« thinking ») | désactivé | `src/clawfedora/openclaw_config.py` |
| Recherche Web | 4 résultats, 4 000 caractères par page | `config/core/web_policy.yaml` |
| Versions d'OpenClaw et d'Ollama | exactes, sans mise à jour automatique | `config/runtime_versions.yaml` |

Les réglages du cloud (budget, limite de clé, modèle, garde-fous) sont dans `config/core/cloud_policy.yaml` ; ils sont décrits plus bas.

Un token est un fragment de mot. En français, compte environ 3 caractères par token.

## Pourquoi 32 768 tokens de contexte

Le contexte est tout ce que le modèle a sous les yeux pour répondre. À chaque message, OpenClaw y place d'abord ses propres consignes, celles du rôle et la description des outils : entre 8 700 et 10 700 tokens selon le rôle. Vient ensuite ta conversation, et il faut garder de la place pour la réponse.

OpenClaw réserve un quart du contexte à la réponse. Avec 8 192 tokens, il ne restait donc rien pour toi. À 32 768, il reste 24 576 tokens pour les consignes et la conversation, et une conversation à son maximum en occupe environ 20 200.

Ces chiffres sont mesurés avec le vrai OpenClaw, par la commande `make native-prompt` du dépôt, qui tourne aussi à chaque modification sur GitHub.

Ce que cette mesure ne dit pas : si 32 768 tokens tiennent dans les 12 Go de ta carte. C'est le rôle de la sonde du [premier essai](02-premier-essai.md).

## Changer la taille du contexte

Si la sonde répond `PARTIAL_CPU_OFFLOAD`, réduis à 16 384. Modifie ces valeurs :

| Fichier | Clé | 32K | 16K |
|---|---|---|---|
| `config/core/openclaw_policy.yaml` | `context_tokens` | 32768 | 16384 |
| `config/core/openclaw_policy.yaml` | `compaction_reserve_tokens` | 8192 | 4096 |
| `config/model_catalog.yaml` | `openclaw_agent_context_tokens` | 32768 | 16384 |
| `config/webui_policy.yaml` | `max_history_bytes` | 32000 | 3000 |

Puis :

```bash
./menu.sh --action validate          # refuse des valeurs incohérentes entre elles
./menu.sh --action install --apply   # réapplique partout
./menu.sh --action context-probe --apply
```

Toutes les générations utilisent le même contexte. C'est voulu : Ollama recharge le modèle à chaque fois que cette valeur change, ce qui prend plusieurs secondes.

À 16K, l'atelier reste utilisable mais le chat a la mémoire courte : il ne transmet plus que 3 000 octets d'historique, environ 500 mots. La raison : OpenClaw réserve un quart du contexte à la réponse, et les consignes fixes occupent déjà environ 10 000 des 12 000 tokens restants. Ces valeurs sont vérifiées avec le vrai OpenClaw ; `make native-prompt` échoue si tu en choisis de trop grandes.

## Réglages du cloud

Fichier : `config/core/cloud_policy.yaml`. `./menu.sh --action validate` refuse les valeurs dangereuses.

| Réglage | Valeur | Remarque |
|---|---|---|
| `budget.monthly_cap_eur` | 25 | Plafond en euros réels. **Borné à 25 dans le code** : un fichier de configuration ne peut pas le relever. |
| `budget.eur_per_usd` | 1,3 | Facteur prudent (change, frais d'achat de crédits, TVA). Doit rester ≥ 1. |
| `budget.alert_ratio` | 0,8 | Seuil d'alerte (80 % du plafond). |
| `budget.recommended_key_limit_usd` | 12 | Limite de clé conseillée. La limite déclarée ne peut pas dépasser `monthly_cap_eur / eur_per_usd` (≈ 19,2 $). |
| `model` | `deepseek/deepseek-v4.1-flash` | Modèle cloud épinglé. |
| `model.context_tokens` | 1 048 576 | Contexte cloud distinct du 32K local. |
| `model.max_output_tokens` | 32 768 | Sortie cloud plus large pour les analyses et livrables complexes. |
| `upstream_params.reasoning.effort` | `xhigh` | DeepSeek est la route de capacité : raisonnement maximal imposé par la passerelle. |
| `provider.sort` | `throughput` | Choisit le fournisseur admissible le plus rapide. |
| `provider.max_price` | 0,25 $ entrée / 0,75 $ sortie par M tokens | Hard cap fournisseur, identique au pire coût réservé localement. |
| `provider.data_collection` | `deny` | Écarte les routes qui ne respectent pas ce réglage. |
| `gateway.port` | 18892 | Boucle locale seulement. |

Le raisonnement long du modèle local reste désactivé pour préserver la latence et la VRAM. DeepSeek n'est pas utilisé comme un simple Qwen distant : la passerelle lui impose `xhigh`, jusqu'à 1M de contexte et 32K de sortie. Le client ne peut ni diminuer ces garde-fous, ni choisir un modèle ou un fournisseur plus cher.

Pour changer le plafond, baisse-le : tu ne peux pas dépasser 25 €. Après toute modification : `./menu.sh --action validate`, puis `./menu.sh --action cloud-enable --value 12 --apply` pour revalider.

## Voix locale

`config/webui_policy.yaml` fixe Whisper `small` sur **CPU/int8**, français, port 18893 en
loopback, audio limité à 25 MiB. Ce choix préserve la B580 pour Qwen. Le modèle Whisper est
préchargé pendant `webui-install --apply`, pas au premier message. La synthèse utilise
`espeak-ng` localement. La qualité et la latence se mesurent avec
[SMOKE_TEST_WEBUI.md](../SMOKE_TEST_WEBUI.md).

## Mode jeu

```bash
./menu.sh --action gaming --apply   # arrête Ollama et OpenClaw, libère la carte
./menu.sh --action daily --apply    # les redémarre
```

Le mode jeu refuse de démarrer si une génération est en cours. Mets d'abord ton projet en pause dans l'atelier.

## Changer de modèle

Le projet est réglé pour un seul modèle. Pour en essayer un autre :

1. Télécharge-le : `ollama pull <nom>`.
2. Dans `config/model_catalog.yaml`, remplace `runtime_id` et `quantization` par ceux du nouveau modèle.
3. Lance `./menu.sh --action install --apply`, puis `./menu.sh --action context-probe --apply`.

Sur 12 Go de mémoire vidéo, un modèle dont le fichier dépasse environ 8 Go ne laissera plus assez de place pour un contexte de 32K. Qwen 3.5 existe aussi en 27B (17 Go) : il ne tient pas sur cette carte.

## Changer de version d'OpenClaw ou d'Ollama

Les versions sont écrites dans `config/runtime_versions.yaml`. L'installation et chaque message vérifient que la version installée est exactement celle-là. C'est une protection : une mise à jour d'OpenClaw peut changer le format de sa configuration.

Pour changer :

1. Sauvegarde : `./menu.sh --action backup`.
2. Modifie la version dans `config/runtime_versions.yaml`, et pour OpenClaw aussi dans `config/core/openclaw_policy.yaml` (deux endroits : `required_version` et le plugin `parallel_search`).
3. `./menu.sh --action validate`.
4. `./menu.sh --action upgrade --apply`.

Si tu proposes ce changement par une pull request, GitHub vérifie automatiquement que la nouvelle version d'OpenClaw accepte la configuration et que le contexte suffit toujours.

## Garder les services actifs sans session ouverte

Par défaut, OpenClaw et le chat s'arrêtent quand tu fermes ta session. Pour les garder actifs :

```bash
scripts/linux/06_install.sh --apply --enable-linger
```
