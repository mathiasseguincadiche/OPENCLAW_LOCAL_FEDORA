# DeepSeek V4 Pro sur OpenRouter — relevé du 2 novembre 2026

[← Revue npm du 2 novembre](README.md) · [Guide cloud](../../fiches/12-cloud.md)

Ce relevé vient de la page publique OpenRouter « DeepSeek V4 Pro 0423 », enregistrée par l'opérateur le 2 novembre 2026. Les valeurs ont été extraites des fiches des fournisseurs intégrées à la page. **Les prix et les fournisseurs changent : revérifier sur openrouter.ai avant un usage régulier.** La page brute n'est pas conservée dans le dépôt.

## Le modèle

- Identifiant API : **`deepseek/deepseek-v4-pro`** (version 0423, publiée le 24 avril 2026).
- Contexte de 1 M de tokens, outils (`tools`, `tool_choice`) et sorties structurées acceptés.
- **Efforts de raisonnement acceptés : `high` et `xhigh` seulement** ; `xhigh` correspond au raisonnement maximal.

## Fournisseurs relevés (prix affichés, $ par million de tokens)

| Fournisseur | Entrée | Sortie | Quantif. | Entraînement | Conserve les prompts | Paramètres absents* |
| --- | --- | --- | --- | --- | --- | --- |
| StreamLake | 0,825 | 1,649 | fp8 | non | **oui** | seed |
| Baidu Qianfan | 0,826 | 1,653 | fp8 | non | **oui** | seed |
| Relace | 0,900 | 1,500 | **fp4** | non | non | seed |
| GMICloud | 0,957 | 1,914 | fp8 | non | **oui** | stop |
| SiliconFlow | 1,000 | 3,135 | fp8 | non | non | stop, seed |
| DigitalOcean | 1,044 | 2,088 | inconnue | non | non | stop, seed |
| Cloudflare | 1,150 | 2,550 | inconnue | non | non | — |
| DeepInfra | 1,300 | 2,600 | fp8 | non | non | — |
| Alibaba Cloud Int. | 1,416 | 2,832 | fp8 | non | **oui** | — |
| Alibaba Cloud Int. (us-east-1) | 1,560 | 3,120 | fp8 | non | **oui** | — |
| NovitaAI | 1,600 | 3,200 | fp8 | non | non | — |
| Venice | 1,650 | 3,301 | inconnue | non | non | seed |
| AtlasCloud | 1,680 | 3,380 | **fp4** | non | **oui** | — |
| Crusoe | 1,740 | 3,480 | fp8 | non | non | — |
| Azure | 1,910 | 3,830 | inconnue | non | non | stop, seed |

\* Parmi `tools`, `tool_choice`, `reasoning`, `max_tokens`, `temperature`, `top_p`, `stop`, `seed`. **Aucun fournisseur ne déclare `parallel_tool_calls`.**

## Ce que la politique en tire (`config/core/cloud_policy.yaml`, modèle `profond`)

- **Confidentialité :** `data_collection: deny`, comme pour le modèle standard. Les fournisseurs qui conservent les prompts sont écartés par OpenRouter.
- **Qualité :** `quantizations: [bf16, fp8, unknown]`, donc pas de version FP4 (Relace, AtlasCloud) pour le raisonnement profond.
- **Prix :** plafonds de **1,40 $ en entrée et 3,20 $ en sortie**. Avec les règles ci-dessus, restent **SiliconFlow, DigitalOcean, Cloudflare et DeepInfra**. Un fournisseur plus cher est refusé par OpenRouter, jamais facturé au-delà. Le budget local réserve le pire cas à ces plafonds.
- **Paramètres :** `require_parameters: true` exclurait tous les fournisseurs si `parallel_tool_calls` était envoyé. Ce champ et `seed` sont retirés pour ce modèle. Une requête avec `stop` n'atteint que Cloudflare et DeepInfra.
- **Effort :** le profil `approfondi` (`xhigh`) est requis. `rapide` et `equilibre` sont refusés avec ce modèle, avec un message explicite.

## Ordre de grandeur du coût

Pour une longue réflexion (30 000 tokens envoyés, 8 000 reçus), au plafond : 30 000 × 1,40 + 8 000 × 3,20 = **0,068 $ (environ 0,09 € au taux prudent de 1,3)**. Une question à un agent en enchaîne souvent plusieurs, avec 3 à 10 retours d'outils. Le plafond de **25 €/mois** reste la limite.
