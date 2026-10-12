# Comment ça marche — l'architecture expliquée simplement

[← Guide](../GUIDE.md) · [Les rôles et outils](07-roles-et-outils.md) · [Un exemple complet](../EXEMPLE_PARCOURS_DEVOPS.md)

## L'idée essentielle

L'atelier sépare **quatre responsabilités** :

1. **Toi, l'utilisateur** : tu exprimes le besoin, choisis le modèle, approuves les étapes et testes les résultats.
2. **Les interfaces et le moteur** : ils organisent les demandes, les tâches, les sources et les confirmations.
3. **OpenClaw et les outils** : ils appliquent les instructions et capacités autorisées au rôle demandé.
4. **Le modèle IA** : il explique et propose, **sans droit d'exécuter du code sur l'hôte**.

> Analogie utile : **Open WebUI est le guichet**, **le moteur de projets est le chef de chantier et son registre**, **OpenClaw distribue la fiche métier**, et **Qwen/DeepSeek propose le travail**. L'analogie s'arrête là : il n'y a pas sept modèles autonomes et le modèle ne signe jamais la réception des travaux.

![Architecture de l'atelier : composants, flux et protections](../diagrams/atelier-architecture.svg)

## Lire le schéma en moins d'une minute

- **À gauche : les portes d'entrée.** Open WebUI pour discuter ; Atelier Projets pour suivre un projet et ses preuves. Les deux utilisent la même logique de projet.
- **Au milieu : le contrôle.** Le pont de chat et le moteur de projets gèrent commandes déterministes, documents, droits, verrou et étapes d'approbation.
- **À droite : le travail du modèle.** OpenClaw applique la mission d'un des sept rôles. Par défaut Ollama exécute Qwen localement sur Fedora/B580.
- **En bas : les sorties durables.** Le projet central contient sources, contexte, fichiers collectés, éléments de preuve et rapports. Un résultat du modèle n'y entre pas librement.
- **Voie cloud facultative :** après autorisation, OpenClaw contacte la passerelle cloud locale qui **filtre et borne** avant OpenRouter/DeepSeek. Elle n'a pas de flèche automatique venant de l'échec du local.

Une flèche indique un **échange de données ou de commandes contrôlées**, pas un droit d'écriture ou d'exécution. Le schéma représente l'architecture **prévue par le code**, pas un test réussi sur le vrai PC.

## À quoi servent les composants ?

| Composant | Sa responsabilité | Sa limite importante |
|---|---|---|
| **Open WebUI** — `127.0.0.1:3000` | Afficher le chat et les fichiers, choisir un rôle, dictée/TTS | Ce n'est pas le moteur de projet ; la plupart des actions complexes nécessitent encore des commandes `!` |
| **Pont de chat** — `127.0.0.1:18891` | Vérifier l'appel, comprendre les commandes `!`, préparer contexte et réponse OpenAI-compatible | Pas d'exécution générale, pas de streaming token par token actuellement |
| **Atelier Projets** — `127.0.0.1:18890` | Interface des étapes, notes, validations et livrables | Ne produit pas lui-même de texte par IA |
| **Worker / moteur** | Ordonnancer les tâches validées, appliquer le verrou, contrôler et collecter les sorties | N'exécute qu'une tâche/génération à la fois |
| **OpenClaw** — Gateway `127.0.0.1:18789` | Charger les consignes et les outils du spécialiste ; appeler le modèle | `exec`, `write`, `edit`, sous-agents et navigateur non autorisés aux rôles quotidiens |
| **Ollama + Qwen** — `127.0.0.1:11434` | Produire les réponses avec le modèle local `qwen3.5:9b-q4_K_M` | Qualité/vitesse/VRAM à mesurer sur la B580 |
| **Toolkit métier** | Recherche locale, trames, lint, génération de fichiers/Draw.io | Les contrôles statiques ne sont pas des tests de déploiement |
| **Passerelle cloud** — `127.0.0.1:18892` | Autoriser, filtrer, réserver le budget puis appeler OpenRouter | Désactivée par défaut ; les contenus métier confidentiels non reconnaissables peuvent échapper au filtre |
| **Voix locale** — `127.0.0.1:18893` | Whisper CPU/int8 et synthèse vocale locale | Fonctionnement du microphone et latence à tester |
| **Projet central** | Sources, index, plans, preuves, exports et décisions approuvées | Les sources deviennent immuables après l'analyse |

Les ports sont **en boucle locale** : l'accès par une tablette distante n'est **pas** ouvert directement par ce dépôt. Il faut une architecture d'accès distant distincte et sécurisée.

## Parcours n° 1 : « Explique-moi ce fichier Terraform »

```text
Utilisateur → Open WebUI → Pont de chat → OpenClaw (rôle DevOps)
                                            ↓
                                     Ollama / Qwen
                                            ↓
                       Explication → Pont → Open WebUI
```

1. Tu choisis **Ingénieur DevOps** et poses ta question.
2. Le pont authentifie la demande et limite le volume d'historique. Avec un petit fichier texte joint hors projet : **4 fichiers/12 000 octets maximum**, chat **local seulement**.
3. Le pont prend le **verrou partagé** et appelle OpenClaw avec le rôle demandé.
4. OpenClaw ajoute ses consignes et éventuellement des outils métier accessibles au rôle.
5. Qwen rédige. Si un outil vérifie un YAML, le résultat reste un **contrôle de syntaxe**, pas un test dans Azure.
6. La réponse revient au chat. **Elle s'affiche en bloc** après la génération. Le bouton d'arrêt peut couper l'affichage sans annuler immédiatement le travail déjà lancé.

**Important :** lire un code source n'autorise pas son exécution. Un fichier téléchargé reste à relire.

## Parcours n° 2 : « Prépare un petit déploiement complet »

```text
Besoin + sources
    ↓
Création du projet (INTAKE_READY)
    ↓
Analyse → questions si besoin → plan de 1 à 4 tâches
    ↓                   accord humain
Tâche Architecte → Tâche DevOps → Tâche Sécurité / Rédacteur si utiles
    ↓
Validation des critères → Audit indépendant de session
    ↓                      corrections si nécessaire
Paquet de livraison → accord humain → COMPLETE
```

**Pourquoi cet ordre ?** L'architecte décrit les flux, le DevOps fournit les fichiers et la méthode de test, la sécurité examine les risques, puis l'auditeur vérifie **preuves et critères**. Ce n'est **qu'un exemple** : le plan peut attribuer les tâches autrement. Le moteur suit les dépendances approuvées, pas un ordre imposé à sept agents.

### Où vont les fichiers ?

- **Intake / sources :** documents d'origine reçus et vérifiés. Une fois analysés, ils ne peuvent plus être remplacés silencieusement.
- **Contexte :** analyse, plan, décisions humaines et index local pour retrouver des passages.
- **Espaces de travail des rôles :** copies et résultats temporaires, distincts de la source de vérité.
- **Collecteur :** vérifie extensions, chemins attendus, limites, empreintes et entrées protégées avant d'accepter une sortie.
- **Livrables et preuves :** fichiers validés ou contrôles consignés dans le projet central. Un PDF n'est pas une preuve de déploiement, et un rapport CI collé par l'IA n'est pas une CI authentifiée.

Les états exacts sont configurés dans `config/core/orchestration_policy.yaml` :

```text
INTAKE_READY → ANALYZED ──→ PLANNED → ASSIGNED → IN_PROGRESS
                   │                                 │
                   └→ CLARIFICATION_REQUIRED          ↓
                       → ANALYZED                VALIDATING ↔ IN_PROGRESS
                                                      ↓
                                              REVIEW ↔ IN_PROGRESS
                                                      ↓
                                            PACKAGING → COMPLETE
```

Les retours vers `IN_PROGRESS` sont des corrections, pas une validation forcée. Une livraison nécessite une confirmation humaine. Le mode guidé n'est activé **que si tu l'as choisi**.

## Parcours n° 3 : la route cloud, uniquement sur accord

```text
OpenClaw → passerelle cloud locale :18892
                      │
           Activation + autorisation ?
                      │ oui
          Analyse des secrets / données
                      │ aucune catégorie bloquante
              Réservation du budget
                      │ sous le plafond
              OpenRouter → DeepSeek
                      │
             Coût réel ou pire cas
                      ↓
           Réponse et journal local
```

**Trois refus différents à ne pas confondre :**

- **Secret détecté :** la passerelle refuse avant l'envoi. Dans le chat, le fil peut rester ensuite en local avec un bandeau ; dans un projet cloud, le traitement se met en pause.
- **Plafond ou fournisseur indisponible :** la réponse cloud n'est pas obtenue. Le chat peut fournir une réponse locale **signalée** ; le projet attend ta décision.
- **Pas d'accord cloud :** le projet reste local. Aucun système ne passe automatiquement du local au cloud.

Le journal borne la dépense **estimée**, mais ne constitue pas une facture. La clé du fournisseur n'est utilisée que par la passerelle. [La procédure complète](12-cloud.md).

## Pourquoi une seule génération à la fois ?

La B580 possède **12 Go de VRAM**. Lancer simultanément plusieurs générations risquerait de saturer la carte ou d'allonger fortement les délais. Le chat, les tâches de projets et les opérations sensibles partagent un **verrou d'inférence**. Une demande concurrente peut donc recevoir « occupé ». Les consultations de statut restent accessibles.

Cette protection est **une règle de capacité**, pas la preuve qu'un contexte de 32K tient effectivement dans la VRAM. [Mesurer la machine](02-premier-essai.md).

## Les contrôles de sécurité, en langage courant

| Protection | Pourquoi elle existe |
|---|---|
| **SELinux et conteneur Podman rootless** | Limiter l'exposition du processus WebUI ; pas d'accès privilégié au PC |
| **Boucle locale `127.0.0.1`** | Ne pas publier les API directement sur le réseau domestique |
| **Pas de shell pour les rôles** | Une instruction erronée ou malveillante ne peut pas lancer `rm`, `terraform apply` ou une autre commande sur l'hôte |
| **Approbation indépendante du modèle** | Une phrase cachée dans un PDF ou une réponse IA ne peut pas signer une étape à ta place |
| **Filtre et budget cloud** | Éviter les secrets évidents et borner les appels payants |
| **Collecte contrôlée** | Protéger les sources et ne publier que les fichiers attendus |
| **Audit** | Distinguer un résultat plausible d'une conformité démontrée |

La validation automatique mesure le code et les contrats du dépôt ; elle ne démontre pas la protection effective du poste contre toutes les attaques.

## Le dépôt : où regarder sans se perdre

```text
README.md                    carte de visite du projet
docs/GUIDE.md                parcours de découverte
docs/fiches/                 modes d'emploi par sujet
docs/diagrams/               schémas lisibles et sources Draw.io
agents/<rôle>/               les consignes propres à chaque spécialité
agents/_shared/              pédagogie, outils et règles communes
config/                      modèle, ports, droits, états et limites
plugins/                     outils métiers et intégration Open WebUI
src/clawfedora/              logique Python du moteur, du pont et du cloud
scripts/linux/               installation, entretien et canary 0.12
tests/                       tests du code et des garde-fous
STATUS.md                    vérifié / restant à vérifier
```

### Les fichiers de configuration les plus utiles

| Modifier / consulter | Où |
|---|---|
| Missions et identifiants | `config/core/agents.yaml` |
| Quels outils sont autorisés | `config/core/tool_policy.yaml` |
| Choix du modèle local/cloud | `config/core/model_routing.yaml`, `config/model_catalog.yaml` |
| États et dépendances des tâches | `config/core/orchestration_policy.yaml` |
| Image Open WebUI, ports et limites | `config/webui_policy.yaml` |
| Permissions, budget et route cloud | `config/core/cloud_policy.yaml` |
| Recherche Web et documents | `config/core/web_policy.yaml`, `config/core/knowledge_policy.yaml` |

**Ne modifie pas directement la configuration générée d'OpenClaw.** Change les sources versionnées du dépôt, exécute `./menu.sh --action validate`, puis applique avec les scripts prévus.

## Ce qui est codé ≠ ce qui est qualifié

Les tests automatiques peuvent contrôler le code Python, Ruff/mypy, ShellCheck, certaines intégrations simulées et la configuration acceptée par OpenClaw. **Ils ne remplacent pas** les essais sur Fedora, la B580, le navigateur Open WebUI réel, les fichiers originaux, le microphone ou un appel facturé par OpenRouter.

La version déployée d'Open WebUI reste **0.11.4** ; `scripts/linux/14_webui_canary.sh` sert à tester **une copie isolée** avec 0.12.0. Les raccourcis visuels ajoutés sont **en lecture seule**, pas une interface complète d'approbation. Le streaming réel n'est pas encore implémenté.

→ [État factuel](../../STATUS.md) · [Plan de validation](../PLAN_QUALITE_2026.md) · [Test de fumée sur Fedora](../SMOKE_TEST_WEBUI.md).

[← Guide](../GUIDE.md) · [Rôles et outils →](07-roles-et-outils.md)
