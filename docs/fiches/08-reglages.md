# Réglages

[← Guide](../GUIDE.md) · [Composants et flux](11-comment-ca-marche.md)

Chaque réglage appartient à une couche précise (interface, pont, moteur de projets, OpenClaw, modèle) : regarde le diagramme avant de modifier un port, un rôle ou une limite.

## Deux modèles locaux, une seule politique de sécurité

Qwen 3.5 9B sert six agents polyvalents ; Ornith 1.5 9B sert l'ingénieur DevOps. Le modèle utilisé ne change **pas** les outils autorisés au rôle. Aucune route d'inférence OpenRouter n'est active.

Le choix des modèles est fixé dans `config/model_catalog.yaml` et `config/core/model_routing.yaml` ; la passerelle et le budget sont déclarés dans `config/core/cloud_policy.yaml`. La route cloud n'est **pas** sélectionnée automatiquement selon la complexité de chaque tâche. [Comprendre la stratégie hybride](../ARCHITECTURE_HYBRIDE.md).

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

## Modèles locaux et retrait de la passerelle

`config/model_catalog.yaml` définit les deux modèles obligatoires et leur quantification. `config/core/model_routing.yaml` définit le modèle de chaque agent. Ils sont chargés alternativement par Ollama ; ne pas forcer plusieurs modèles sur la B580 de 12 Go.

Après sauvegarde, `./menu.sh --action local-retire-cloud --apply` arrête l'ancien service OpenRouter et retire ses anciens secrets locaux. Les anciennes commandes d'activation n'existent plus.

[Architecture et critères de qualification](../ARCHITECTURE_LOCALE_QWEN_ORNITH.md).

## Préférences d'apprentissage et mémoire approuvée

Dans l'Atelier Projets, **Mon accompagnement et la continuité du chat** comporte cinq notes de suivi et deux champs de pédagogie : `explanation_style` (manière souhaitée d'apprendre) et `learning_summary` (acquis qu'on veut conserver). Les sept champs sont facultatifs, chacun limité à 500 caractères ; seul l'utilisateur peut valider leur enregistrement. La fiche est injectée au mentor comme donnée de contexte, sans certifier d'acquis et sans création automatique d'une mémoire par l'IA. Voir [Apprendre](05-apprendre.md) et [qualification pédagogique /20](../EVALUATION_PEDAGOGIE.md).

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

## Recherche Web : mode privé ou connecté

L'inférence Qwen peut rester locale même si les outils Web consultent Internet. Pour interdire les outils Web des **sept rôles** après installation, lancer `./menu.sh --action web-private --apply`. La procédure applique le nouveau contrat et vérifie que le Gateway redémarre ; les modèles Ollama restent locaux, même quand un outil Web consulte des sources publiques. Voir [la procédure et ses limites](../WEB_ACCESS_PRIVATE_MODE.md).
