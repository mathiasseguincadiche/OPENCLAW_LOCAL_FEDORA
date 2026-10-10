# Le cloud, facultatif

[← Guide](../GUIDE.md)

Par défaut, tout reste sur ton PC avec Qwen. Le cloud est une option que tu actives toi-même, pour les moments où un modèle plus puissant aide : expliquer une notion publique, relire un long texte. Le modèle cloud est **DeepSeek V4.1 Flash**, appelé par OpenRouter.

Tant que tu n'as rien activé, rien de cette fiche ne s'applique : aucune conversation ni aucun projet ne part vers un modèle distant (seule la recherche Web des rôles, quand tu la demandes, sort pour interroger le Web).

## Le principe : local d'abord, cloud sur demande

| Où | Comportement |
|---|---|
| Chat, modèle « · local » | Qwen sur ton PC. Aucun contenu de la conversation ne part vers un modèle distant. C'est le mode **Travail**. |
| Chat, modèle « · cloud (DeepSeek) » | DeepSeek via la passerelle. C'est le mode **Apprendre**, pour des questions publiques. |
| Atelier Projets | Local, sauf pour un projet que tu autorises toi-même, un par un. |

Rien ne passe au cloud sans que tu l'aies choisi : ni une conversation, ni un projet. Rien ne repasse non plus du local vers le cloud tout seul.

## Comment ça protège ce qui part

OpenClaw ne parle jamais à OpenRouter. Il parle à une **passerelle locale** (`127.0.0.1:18892`) qui est la seule à connaître ta clé OpenRouter. Avant chaque envoi, la passerelle :

1. vérifie que la demande vient bien d'OpenClaw (jeton local) ;
2. **filtre tout le contenu** qui partirait : consignes, historique, contexte ajouté, appels et **résultats d'outils** ;
3. **réserve le coût** maximal de l'appel dans le budget du mois ;
4. envoie, puis note le coût réel.

Un tour où un rôle utilise un outil fait **deux appels facturés** (la demande, puis la suite avec le résultat de l'outil). Les deux passent par la passerelle : les deux sont filtrés et comptés.

### Ce que le filtre arrête

Clés privées, jetons (GitHub, GitLab, OpenRouter, Anthropic, Slack, JWT), identifiants de services cloud (AWS, Google, Azure), mots de passe et secrets affectés dans du code ou de la configuration, identifiants intégrés dans une URL, identifiants réels d'abonnement ou de tenant. Les exemples de cours (`password = var.pwd`, un GUID d'exemple, une clé `EXAMPLE`) passent.

Tu peux ajouter **tes propres termes sensibles** (nom d'employeur, serveur interne) dans `/srv/openclaw-local/state/cloud/denylist.txt`, une ligne par terme. Une ligne `re:motif` est une expression régulière. Le fichier est relu dès qu'il change.

### Ce que le filtre n'arrête pas

Un contenu confidentiel qui n'a pas l'allure d'un secret : le nom d'un serveur interne, la configuration de ton employeur, un document de travail. Un filtre ne peut pas le reconnaître. C'est le rôle du mode **Travail** (local) et de ta liste de termes. En cas de doute, reste en local.

Les messages de blocage nomment la **catégorie** trouvée (« jeton d'accès », « mot de passe »), jamais la valeur.

### Où part ce que tu envoies

DeepSeek V4.1 Flash est appelé via OpenRouter. La passerelle impose `data_collection: deny`, `require_parameters: true`, un tri `throughput` et un `max_price` correspondant au pire coût réservé. Si aucun endpoint ne respecte ces contraintes, l'appel échoue : le projet ne relâche jamais automatiquement la confidentialité ou le plafond de prix. Vérifie aussi les conditions du fournisseur réellement retenu lors du premier essai.

## Le budget : 25 € réels par mois

Trois protections indépendantes :

| Protection | Ce qu'elle fait | Qui la tient |
|---|---|---|
| **Crédits prépayés**, sans rechargement automatique | Plafond d'achat réel : OpenRouter ne peut pas débiter au-delà de ce que tu as mis | toi, chez OpenRouter |
| **Limite posée sur la clé** | OpenRouter coupe la clé quand elle est atteinte | toi, chez OpenRouter |
| **Journal local** | Refuse un appel qui dépasserait le plafond et compte chaque appel | la passerelle |

**Pourquoi la limite de la clé est en dollars.** Ton plafond est de 25 € payés, mais OpenRouter compte en dollars. Un dollar de consommation coûte plus d'un euro une fois le change, les frais d'achat de crédits et la TVA ajoutés. Le journal applique un facteur prudent de **1,3 € par dollar** (`eur_per_usd` dans `config/core/cloud_policy.yaml`). Donc : 25 € ÷ 1,3 ≈ **19,2 $** au maximum sur la clé, et la commande d'activation refuse une limite plus haute. **12 $** est la valeur conseillée : environ 15,6 €, avec de la marge pour un usage estimé à 6-10 $ par mois.

Ce que compte le journal : le coût réel quand OpenRouter le donne, sinon les jetons × le tarif plafond. Le même plafond est transmis à OpenRouter avec `provider.max_price`, donc une route plus chère est refusée **avant** l'appel. Un appel interrompu, sans information de coût ou jamais réglé est compté au pire cas. Seul un refus net du fournisseur n'est pas compté. À 80 % du plafond, le chat et le tableau de bord le disent ; à 100 %, plus rien ne part.

Le facteur 1,3 est une marge, pas un taux mesuré, et les tarifs de référence sont ceux du dépôt. Le relevé OpenRouter reste la vérité : une fois par mois, enregistre-le (voir plus bas).

## Activer le cloud

### Chez OpenRouter (à faire toi-même)

1. Crée un compte et règle la politique de données de façon restrictive (refuser les fournisseurs qui conservent ou entraînent sur tes données). Les intitulés exacts de ces pages changent : vérifie-les sur le site.
2. Achète des crédits **prépayés** avec le **rechargement automatique désactivé**. Pour commencer, un montant inférieur à 25 €.
3. Crée une clé API et pose-lui une **limite de crédit en dollars**, au plus 19,2 $ (12 $ conseillés).

### Sur ton PC

```bash
./menu.sh --action cloud-set-key                         # saisie masquée de la clé
./menu.sh --action cloud-enable --value 12               # contrôles, rien n'est activé
./menu.sh --action cloud-enable --value 12 --apply       # active le cloud
./menu.sh --action cloud-status                          # état, budget du mois
```

`--value` est la limite posée sur la clé, en dollars. La commande te demande de confirmer que les crédits sont prépayés sans rechargement automatique.

Les contrôles ne s'arrêtent pas au constat : la commande démarre la vraie passerelle avec le vrai filtre et le vrai journal devant un faux fournisseur, et vérifie qu'un secret est bloqué **avant** toute réservation et tout envoi, qu'un appel sain est relayé avec ta clé seule et compté, et qu'un appel au-delà du plafond est refusé **avant** de partir. Elle interroge aussi OpenRouter pour lire la limite réelle de ta clé. Si un contrôle échoue, **le cloud reste désactivé** et tu vois lequel.

Avec `--apply`, la commande écrit l'activation, démarre le service `clawfedora-cloud-gateway`, régénère la configuration d'OpenClaw avec le fournisseur cloud et redémarre le pont du chat.

### Revenir en arrière

```bash
./menu.sh --action cloud-disable --apply
```

Le cloud est désactivé, la passerelle arrêtée et le fournisseur retiré de la configuration d'OpenClaw. Tout redevient local.

### Enregistrer ce qu'OpenRouter a facturé

```bash
./menu.sh --action cloud-reconcile --value 18.40 --apply   # montant en euros
```

Le plafond applique **le plus élevé** de l'estimation du journal et du montant déclaré.

## Capacité DeepSeek

La route cloud est volontairement plus généreuse que Qwen local :

- contexte déclaré : **262 144 tokens** ;
- sortie maximale : **16 384 tokens** ;
- raisonnement : **`xhigh`**, imposé par la passerelle ;
- historique WebUI transmis : jusqu'à environ **768 Ko** avant réduction ;
- routage fournisseur : priorité au débit, mais uniquement sous le plafond de prix et les règles de données.

Ces valeurs ne rendent pas chaque question lente par obligation : elles donnent à DeepSeek la place
nécessaire pour les dépôts, documents et boucles d'outils complexes. Le modèle local reste le choix
quotidien pour le privé et les petites demandes.

## Dans le chat : Apprendre ou Travail

Quand le cloud est activé, Open WebUI liste chaque rôle deux fois : « · local » et « · cloud (DeepSeek) ». Choisir le modèle, c'est choisir le mode.

- Une réponse cloud commence par un bandeau « ☁️ Réponse du modèle cloud ». Dès 80 % du budget, il ajoute la dépense du mois.
- **Le choix par défaut reste local.** Rien ne part au cloud tant que tu n'as pas choisi le modèle cloud, ou réglé toi-même le modèle par défaut dans Open WebUI.
- Si le filtre détecte un secret, **la conversation passe en local** : tu vois « 🔒 Conversation passée en local » et les réponses suivantes de ce fil restent locales, pour que la suite ne reparte pas au cloud avec le même historique.
- Si le cloud est indisponible ou le plafond atteint, la réponse vient du local avec un bandeau « 💻 Réponse locale : … ». Le fil ne se verrouille pas.

## Dans l'atelier : un accord par projet

Ouvre le projet : le panneau **Cloud pour ce projet** affiche le texte d'accord. Coche la case puis clique **Autoriser le cloud pour ce projet**. En ligne de commande : `clawfedora project cloud-approve --project-id mon-projet --acknowledge`.

- L'accord n'est possible que si le cloud est activé.
- Il couvre tout le projet : cadrage, plan, tâches, audits, retour sur ton travail. La réparation d'un JSON mal formé reste locale.
- Il est lié aux **sources** du projet. Si elles changent, il faut approuver à nouveau.
- Sans accord, le projet fonctionne exactement comme avant.

### Pause visible

Si une étape cloud ne peut pas s'exécuter, **le projet se met en pause** et la raison s'affiche sur sa carte. La tâche n'est ni échouée ni refaite en local.

| Raison | Que faire |
|---|---|
| Le filtre a bloqué un envoi (catégorie nommée) | Retirer ce contenu des sources, ou retirer l'accord cloud |
| Plafond mensuel atteint | Attendre le mois suivant, ou retirer l'accord cloud |
| Fournisseur indisponible ou réponse coupée | Réessayer plus tard |
| Passerelle injoignable | Vérifier `systemctl --user status clawfedora-cloud-gateway` |
| Cloud désactivé après l'accord | Réactiver le cloud, ou retirer l'accord |
| Sources modifiées depuis l'accord | Approuver à nouveau |

Pour **poursuivre en local**, tu dois le décider : clique **Retirer l'accord cloud**, puis **Reprendre**. La tâche repart de zéro en local. Pour **rester au cloud**, corrige la cause puis reprends ; si elle persiste, le projet se remet en pause.

Chaque projet affiche le dernier modèle utilisé, le nombre d'appels cloud et un coût **estimé prudent**. Le pied de page affiche la dépense du mois sur 25 €.

## Quand ça ne va pas

| Symptôme | Piste |
|---|---|
| `cloud-enable` échoue sur « clé du fournisseur » | Relance `cloud-set-key` ; la clé doit commencer par `sk-or-` |
| « plafond chez le fournisseur » | Confirme le prépayé et donne une limite ≤ 19,2 $ |
| « limite de clé (en ligne) » | La clé n'a pas de limite de crédit, ou son plafond dépasse celui que tu as déclaré : corrige chez OpenRouter |
| Le modèle « · cloud » n'apparaît pas dans Open WebUI | Le cloud n'est pas activé : `cloud-status` |
| Chaque appel cloud est refusé en 402 | Plafond atteint, ou journal du budget illisible : `cloud-status` |
| OpenRouter répond « no endpoints » (404) | Aucun hébergeur du modèle ne remplit `data_collection: deny`. Ne relâche pas ce réglage sans avoir lu la politique de données de l'hébergeur : voir [Quel modèle pour expliquer](../DECISION_MODELE.md) |
| Un blocage te semble à tort | Le message nomme la catégorie ; vérifie `denylist.txt` |
| Après une restauration, le cloud ne marche plus | La sauvegarde ne contient pas ta clé : relance `cloud-set-key`, puis `cloud-enable` |
| Tu veux changer de clé | `cloud-set-key` propose de remplacer la clé existante |

## Sauvegardes

Les sauvegardes ne sont pas chiffrées. Elles **ne contiennent ni ta clé OpenRouter ni le jeton local de la passerelle** : après une restauration, saisis la clé de nouveau. Elles contiennent le journal du budget, l'état d'activation et ta liste de termes sensibles.

## Ce qui est vérifié, et ce qui ne l'est pas

Vérifié automatiquement : le filtre sur tous les chemins du contenu (y compris les résultats d'outils), le comptage de chaque appel, le refus au plafond avant l'envoi, la pause sans bascule locale, avec le vrai OpenClaw et un faux fournisseur.

**Jamais essayé avec le vrai OpenRouter sur le PC cible** : la qualité réelle de DeepSeek, le coût d'un tour avec outils, le provider admissible sous `data_collection: deny` + `max_price`, la forme exacte de la réponse qui donne la limite de ta clé et le service sur Fedora restent à valider. Suis [SMOKE_TEST_WEBUI.md](../SMOKE_TEST_WEBUI.md).

## Test de fumée à faire une fois

À la première réponse cloud, vérifie aussi que le routage fonctionne avec la politique de données de la passerelle (erreur « no endpoints » : voir le tableau ci-dessus).

1. `./menu.sh --action cloud-status` : « ready=1 », budget à 0 €.
2. Dans Open WebUI, pose une question publique au modèle « · cloud (DeepSeek) » : le bandeau cloud apparaît. Note le coût dans `cloud-status`.
3. Dans la même conversation, colle un faux jeton (ex. `ghp_` suivi de 36 lettres au hasard) : la conversation passe en local, avec le bandeau 🔒.
4. Dans l'atelier, autorise un petit projet de test, lance une tâche, puis arrête le service (`systemctl --user stop clawfedora-cloud-gateway`) et relance : le projet doit se mettre en pause avec une raison, sans rien exécuter en local.
5. `./menu.sh --action cloud-disable --apply`, puis redémarre : tout doit marcher en local, hors ligne.

Compare à la fin le coût affiché avec le relevé OpenRouter, et enregistre-le avec `cloud-reconcile`.
