# Passerelle cloud locale : conception et faits vérifiés

**Statut : tout est en place (lots 3 à 8) : fondation, exécuteur, passerelle et filtre, modes Apprendre/Travail, budget et activation contrôlée, accord par projet dans l'atelier. Le cloud reste désactivé tant qu'il n'est pas activé par `cloud-enable --apply`. Il n'a jamais été essayé avec le vrai OpenRouter.**

Ce document décrit la conception, fixe le contrat que le code respecte (imposé par `clawfedora validate`) et consigne ce qui a été **vérifié avec le vrai OpenClaw 2026.9.8** (`make native-cloud`, `make native-schema`, `make native-prompt`).

## Principe

OpenClaw ne parle jamais à OpenRouter. Il parle à une passerelle en boucle locale (`127.0.0.1:18892`, `config/core/cloud_policy.yaml`), qui seule lit la clé du fournisseur, filtre tout le contenu sortant, réserve et compte chaque appel facturé, puis transmet à OpenRouter.

```
OpenClaw ──► fournisseur "cloudgw" (127.0.0.1:18892/v1) ──► [filtre + budget] ──► OpenRouter
```

## Faits vérifiés

| Question | Constat |
|---|---|
| OpenClaw accepte-t-il un fournisseur personnalisé à URL locale ? | Oui. `models.providers.cloudgw`, `api: openai-completions`, modèles déclarés statiquement, `models.mode: replace` : aucune découverte de catalogue, donc aucun accès réseau au démarrage. |
| Peut-on choisir le modèle par requête ? | Oui : `openclaw agent --model cloudgw/deepseek/deepseek-v4.1-flash`. Les sept rôles gardent Qwen comme modèle principal ; le cloud se choisit à chaque tour. |
| Qui voit quoi ? | La passerelle reçoit le prompt système, l'historique et, au second appel d'une boucle d'outil, **les résultats d'outils**. Un tour avec un outil fait **deux appels facturables**. |
| Quel jeton circule ? | Un jeton **local** (`Authorization: Bearer <jeton local>`), lu dans la variable `CLAWFEDORA_CLOUD_GATEWAY_TOKEN`. La clé du fournisseur n'atteint jamais OpenClaw : le contrôle fait échouer toute fuite. |
| Usage en streaming ? | OpenClaw envoie `stream: true` et `stream_options.include_usage: true` ; l'usage et le coût peuvent donc être lus dans le dernier fragment. |
| Peut-on piloter le raisonnement ? | Oui par la **passerelle**, pas par le client : elle injecte `reasoning.effort=xhigh` dans chaque requête DeepSeek. Le modèle ou Open WebUI ne peuvent pas affaiblir ce réglage. |
| Que se passe-t-il si le jeton manque ? | OpenClaw résout les secrets de **tous** les fournisseurs avant un tour : un jeton absent fait échouer **même un tour local**. L'environnement d'exécution doit donc toujours définir ce jeton dès que le fournisseur est configuré (lot 4). Avec le jeton défini et la passerelle arrêtée, les rôles locaux fonctionnent (`make native-prompt`). |
| Retour arrière | Désactiver le cloud supprime le fournisseur `cloudgw` d'une installation existante (migration vérifiée par `make native-schema`). |
| Quels modèles `--model` peut-il choisir ? | Seulement ceux de `agents.defaults.modelPolicy.allow` : Qwen, et le modèle cloud uniquement si le cloud est activé. |

## Exécuteur (lot 4)

`openclaw_runner(...)(role, prompt, session)` garde son comportement local. Un appelant qui a décidé d'utiliser le cloud passe `route="cloud"` ; rien ne bascule jamais seul du local vers le cloud.

- **Refus avant tout processus** : la route cloud exige un enregistrement d'activation (`state/cloud/activation.json`) prouvant que **chaque** contrôle requis par la politique (`privacy_filter`, `budget_guard`) est vérifié. Un seul contrôle vérifié ne suffit pas. Seule la future commande d'activation (lot 6) écrit cet enregistrement ; `revoke_activation` éteint le cloud.
- **Pas d'Ollama sur la route cloud** : ni version, ni inventaire, ni verrou de digest. Le tour passe par `openclaw agent --model cloudgw/deepseek/deepseek-v4.1-flash` via la Gateway OpenClaw.
- **Configuration revérifiée** avant un tour cloud (avec le vrai CLI) : l'URL du fournisseur doit être exactement celle de la politique, le transport, le modèle déclaré, la liste d'autorisation, et la clé doit être une **référence d'environnement** (jamais une chaîne). `config get` masque le nom de la référence (`__OPENCLAW_REDACTED__`) mais garde sa forme : c'est cette forme qui est contrôlée.
- **Identité du modèle** : le tour échoue si le fournisseur ou le modèle réellement servis diffèrent. `state/model-runs/<session>.json` conserve route, fournisseur, modèle et tokens, **sans contenu**.
- **Jeton local** : `state/cloud/gateway.token` (droits 0600, répertoire 0700, créé une fois). L'environnement d'exécution le définit toujours (voir plus haut pourquoi). Hors d'un runtime géré, rien n'est écrit.
- **Réparation JSON** : écart assumé par rapport au plan initial (« sur la même route »). Une syntaxe JSON invalide renvoyée par le cloud est réparée **par le modèle local**, qui ne fait sortir aucune donnée et ne coûte rien. Si Ollama est indisponible, la tâche échoue (« relancer la tâche ») : un second appel cloud facturé n'a jamais lieu pour réparer.

Vérifié avec le vrai OpenClaw 2026.9.8 par `make native-cloud` : une vraie Gateway est démarrée, la route cloud est d'abord refusée, puis acceptée après activation ; la passerelle factice voit le jeton local, deux appels pour un tour avec un outil, et l'identité est enregistrée.

## Passerelle, filtre et modes (lot 5)

`python -m clawfedora.cloud_gateway --root … --runtime-root …` lance la passerelle sur `127.0.0.1:18892`. Pour **chaque** requête, dans cet ordre, et avant que quoi que ce soit ne parte :

1. le jeton local est vérifié en temps constant, ainsi que l'en-tête `Host` (401 sinon) ;
2. le cloud doit être activé (503 sinon) ;
3. la requête est bornée (taille, nombre de messages et d'outils) et **normalisée sur liste blanche** : `models`, `route`, `provider`, `plugins`, `transforms`, `reasoning`… sont refusés (400), de sorte qu'un client ne peut ni détourner vers un modèle plus cher ni modifier les réglages de la politique ; le modèle est forcé, la sortie bornée ;
4. le filtre de confidentialité lit **tout le corps** : prompt système, historique, contexte ajouté, arguments d'appels d'outils et **résultats d'outils** (451 sinon) ;
5. le budget réserve le coût maximal (402 sinon) ;
6. la passerelle injecte `data_collection: deny`, `require_parameters`, le tri `throughput`, le hard cap `max_price`, `reasoning.effort=xhigh` et `usage`, puis appelle le fournisseur avec **sa** clé, relaie la réponse et règle l'usage réel.

Un client qui se déconnecte en plein flux n'interrompt pas la lecture : le fournisseur continue de générer et de facturer, l'usage est lu jusqu'au bout. Un appel sans usage connu garde l'estimation maximale (`interrupted`) ; un appel refusé par le fournisseur la libère (`failed`).

`state/cloud/events.jsonl` (0600) journalise chaque décision **sans contenu ni secret** (catégories, estimation, usage, coût).

### Filtre de confidentialité

Bloque : clés privées, identifiants et clés de services cloud (AWS, Google, Azure : clés de stockage, SAS, secrets applicatifs), jetons (GitHub, GitLab, OpenRouter, Anthropic, OpenAI, Slack, JWT), identifiants dans une URL, valeurs d'allure aléatoire affectées à un mot de passe, une clé ou un jeton, identifiants d'abonnement ou de tenant **réels**, tout contenu non textuel, et les termes de `state/cloud/denylist.txt` (un par ligne, ou `re:motif`).

Laisse passer ce qui sert au cours : plages d'adresses de documentation, adresses privées, `example.com`, références (`var.x`, `{{ vault }}`, `${{ secrets.X }}`), mots de passe d'exemple à faible entropie, exemples canoniques des fournisseurs (`…EXAMPLE`, GUID à zéros ou séquentiels), et les sept prompts des rôles (testés).

**Limite assumée** : un filtre ne reconnaît pas ce qui est confidentiel sans ressembler à un secret (configuration d'un employeur, nom d'un serveur interne). C'est le rôle du mode **Travail** et de la liste personnelle.

### Modes dans Open WebUI

Le mode est le choix du modèle. Sans cloud activé, rien ne change : sept rôles locaux. Cloud activé, chaque rôle apparaît deux fois (« · local » et « · cloud (DeepSeek) »). Une réponse cloud porte un bandeau de provenance. Si le cloud ne peut pas répondre, la réponse locale est donnée **avec un bandeau visible** :

- le filtre a détecté quelque chose (sur le message, le contexte ou, par le journal de la passerelle, un résultat d'outil) : la conversation **passe en local et y reste**. La passerelle de chat ne garde aucun état ; chaque réponse suivante répète le marqueur « 🔒 Conversation passée en local », qui est relu dans l'historique ;
- budget épuisé, fournisseur indisponible : repli local ponctuel, sans verrouiller le fil.

Les bandeaux sont retirés de l'historique renvoyé au modèle. Un test de repli utilise toujours une **nouvelle session** pour ne pas laisser un tour cloud à moitié fait.

### Faits établis avec le vrai OpenClaw (`make native-cloud`)

- **OpenClaw masque lui-même les jetons** dans les résultats d'outils avant de les envoyer au modèle (`ghp_Zq…7Zq7`) : première protection native. Le filtre de la passerelle protège ce qu'OpenClaw ne sait pas reconnaître (identifiant d'abonnement, termes personnels).
- **Les statuts 401, 402, 403 et 429 de la passerelle sont interprétés comme un échec d'authentification ou de facturation du fournisseur** : OpenClaw met alors le fournisseur en pause environ une minute (« Inline API key … temporarily disabled »). Un blocage du filtre est propre à une requête : il répond donc **451**, qui ne déclenche pas cette pause, pour que la requête saine suivante passe. Le budget épuisé reste en 402 : s'arrêter est justement l'effet voulu.
- Un tour cloud de bout en bout (vraie Gateway, vraie passerelle, faux fournisseur) : deux appels comptés pour un tour avec un outil, un secret dans le message bloqué avant tout envoi, un secret n'apparaissant que dans un résultat d'outil (fichier lu par l'agent) bloqué avant tout envoi, la clé du fournisseur absente de tout fichier hors de la passerelle.

## Budget et activation (lot 6)

### Trois couches pour tenir 25 € réels

| Couche | Rôle | Qui la tient |
|---|---|---|
| Crédits **prépayés**, sans rechargement automatique | Plafond d'achat réel : au pire, ce qui est dans le compte | OpenRouter, vous |
| Limite de crédit posée **sur la clé** | Le fournisseur coupe lui-même la clé | OpenRouter |
| Journal local (`state/cloud/ledger-AAAA-MM.jsonl`) | Refuse avant l'envoi, compte chaque appel | la passerelle |

Le journal compte en euros avec un facteur pessimiste `eur_per_usd: 1.3` (change, frais d'achat de crédits, TVA). Le plafond est borné en code à 25 € : aucun fichier de configuration ne peut le relever. La limite de clé déclarée ne peut pas dépasser `25 / 1,3 ≈ 19,2 $` (12 $ recommandés).

### Règle de comptage

Un appel = deux lignes : une **réservation** du pire coût (toute l'entrée, sortie au maximum), écrite avant l'envoi, et un **règlement** après.

| Situation | Compté |
|---|---|
| Réponse avec coût fourni par le fournisseur | le coût réel |
| Réponse sans coût mais avec les jetons | jetons × tarif de référence |
| Réponse sans usage, flux coupé, client parti, fournisseur injoignable, plantage avant règlement | **le pire cas réservé** |
| Refus net du fournisseur (4xx/5xx avec réponse) | rien (réservation libérée) |
| Filtre de confidentialité | rien : rien n'a été réservé ni envoyé |

Un tour d'agent avec un outil fait deux appels facturés ; les deux passent par la passerelle donc les deux sont comptés. Le journal est protégé par un verrou de fichier et un verrou de thread, écrit avec `fsync`, en 0600 ; une dernière ligne tronquée par un plantage est ignorée, toute autre ligne illisible **arrête le cloud** (refus 402) plutôt que de deviner.

### Rapprochement avec la facture

`./menu.sh --action cloud-reconcile --value 18.40 --apply` enregistre le montant réellement facturé ce mois-ci par OpenRouter. Le plafond applique **le plus élevé** de l'estimation locale et du montant déclaré. Les relevés d'OpenRouter restent la référence : le journal est une protection, pas une facture.

### Activation : `./menu.sh --action cloud-enable --value 12 --apply`

1. `cloud-set-key` : la clé est saisie masquée, jamais en argument, écrite en 0600 dans le seul fichier lu par la passerelle.
2. `cloud-enable` lance les contrôles sans réseau ni clé réelle, puis, si vous avez confirmé les crédits prépayés, interroge `GET /key` chez OpenRouter pour lire la limite réelle de la clé (la seule requête réseau de la commande).
3. Le contrôle décisif démarre la **vraie** passerelle, le **vrai** filtre et le **vrai** journal devant un faux fournisseur : jeton faux refusé, secret bloqué avant toute réservation, appel sain relayé avec la clé du fournisseur seule et compté, appel au-delà du plafond refusé avant l'envoi.
4. Seulement si tout passe **et** avec `--apply`, `activation.json` est écrit, le service systemd utilisateur `clawfedora-cloud-gateway` démarre, la configuration OpenClaw est régénérée avec le fournisseur `cloudgw` et le pont du chat est redémarré.
5. `cloud-disable --apply` fait le chemin inverse : activation retirée, service arrêté, `cloudgw` retiré de la configuration.

Sans `--apply`, rien n'est activé et aucun service n'est touché. Le pont ajoute sous le bandeau cloud une ligne de budget à partir de 80 % du plafond.

## Atelier Projets (lot 7)

L'Atelier n'envoie rien au cloud par défaut. Un projet n'y passe qu'après **son** accord explicite.

### Accord par projet
- Depuis le tableau de bord (« Autoriser le cloud pour ce projet… », texte à lire et case à cocher) ou `clawfedora project cloud-approve --acknowledge`.
- Impossible tant que le cloud n'est pas activé (lot 6). L'accord est un fichier privé (0600) dans `state/project-cloud/`, sans aucun contenu du projet.
- L'accord est **lié aux sources** : empreinte SHA-256 de `intake/` et `sources/` au moment de l'accord. Si les sources changent, l'état devient « à renouveler » et rien ne part au cloud avant un nouvel accord.
- Le texte d'accord dit ce qui part (consignes, extraits lus par les agents, résultats d'outils, après filtrage), ce que le filtre ne reconnaît pas (un contenu confidentiel sans allure de secret) et ce qui se passe en cas de blocage.
- Aller au cloud couvre toutes les étapes du projet : cadrage et plan, tâches, audits, retour sur un travail rendu. La réparation d'un JSON malformé reste toujours locale.

### Pause visible, jamais de bascule silencieuse
Quand une étape cloud ne peut pas s'exécuter, la tâche **n'est ni échouée ni refaite en local** : le projet passe en pause et la raison s'affiche sur la carte du projet et dans son panneau.

| Cause | Lecture |
|---|---|
| `privacy_blocked` | le filtre a bloqué un envoi ; les **catégories** sont nommées, jamais la valeur |
| `budget_refused` | plafond mensuel atteint (contrôlé aussi avant tout appel) |
| `provider_unavailable` | erreur du fournisseur, réponse coupée |
| `gateway_unreachable` | aucune trace de la passerelle (service arrêté ?) |
| `cloud_inactive` | le cloud a été désactivé après l'accord |
| `consent_stale` | sources modifiées depuis l'accord |

La cause est lue dans le journal de la passerelle (sans contenu). Une réponse du cloud dont le contenu est mauvais (JSON invalide, critères non remplis) reste un échec de tâche ordinaire, pas une pause.

Pour **continuer en local**, il faut le décider : « Retirer l'accord cloud » (ou `cloud-revoke`), puis reprendre. La tâche repart de zéro en local. Pour **rester au cloud**, corriger la cause puis reprendre ; si elle persiste, le projet se remet en pause au lieu de boucler.

### Modèle et coût affichés
- Chaque appel est consigné par projet (route, modèle réellement utilisé tel que rapporté par OpenClaw, tâche, coût) dans `state/project-cloud/<projet>.runs.jsonl`.
- Le coût d'un appel est la **différence du journal budgétaire** avant et après (estimation prudente en euros, pire cas compris). Comme une seule tâche ou discussion tourne à la fois (verrou), cette attribution est exacte pour le projet.
- Le pied de page du tableau de bord montre la dépense du mois sur 25 € et le seuil d'alerte.

### Limites de l'atelier
- Le routage est testé avec un faux exécuteur qui imite le journal de la passerelle ; la lecture de la cause suppose que le journal contient les décisions décrites ci-dessus (c'est testé côté passerelle au lot 5).
- Si le journal de la passerelle ne contient aucune trace pendant l'échec, la pause est `gateway_unreachable` : une panne d'OpenClaw lui-même avant tout appel est donc présentée comme une panne de la passerelle.
- Le coût d'une tâche inclut les appels de sa session seulement ; une discussion Open WebUI en cloud n'est pas rattachée à un projet.

## Contrats imposés par `clawfedora validate`

- Cloud désactivé par défaut (`enabled_by_default: false`) ; l'activation est une décision d'exécution, hors dépôt.
- Aucun repli du local vers le cloud ni vers un modèle caché. Le repli cloud vers local est possible, mais visible.
- Confidentialité **et** budget sont tous deux requis (`requires`).
- Passerelle sur `127.0.0.1`, port valide non utilisé, jeton nommé par variable d'environnement, fichier de clé relatif à l'état d'exécution.
- Le cloud peut dépasser les limites du petit modèle local : contexte 32K..1M et sortie 4K..32K, sans jamais être inférieurs au local.
- `data_collection: deny`, `require_parameters: true`, `sort: throughput`, `reasoning: xhigh` et `max_price` égal au pire tarif réservé sont imposés.
- Le modèle cloud est déclaré au catalogue, optionnel, et chaque rôle pointe vers lui.

## Ce qui n'est pas prouvé

- Les tarifs de référence sont ceux du dépôt, pas ceux affichés par OpenRouter aujourd'hui ; le coût réel renvoyé dans `usage.cost` prime, mais si le fournisseur ne le renvoie pas, le comptage retombe sur ces tarifs.
- Le facteur 1,3 est une marge, pas un taux mesuré. Seul le relevé OpenRouter dit ce qui est réellement prélevé : d'où le rapprochement manuel.
- La vérification en ligne de la limite de clé n'a pas été exécutée contre le vrai fournisseur (pas de clé ici) : elle est testée avec un faux, sur la forme de réponse que je connais de `GET /api/v1/key` (`data.limit`), **non vérifiée** ici faute d'accès à la documentation du fournisseur : si la forme diffère, le contrôle échoue et l'activation reste refusée.
- Le service systemd et le script d'activation n'ont pas tourné sur Fedora ; les contrôles couvrent leur syntaxe et leur ordre, pas leur exécution.

Aucun appel réel vers OpenRouter, aucun comportement de GLM, aucun essai sur le PC Fedora. Les tests utilisent une passerelle factice.
