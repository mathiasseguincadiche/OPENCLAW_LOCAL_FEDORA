# Exemple commenté — préparer le déploiement d'une petite API

[← Guide](GUIDE.md) · [Choisir les rôles](fiches/07-roles-et-outils.md) · [Architecture expliquée](fiches/11-comment-ca-marche.md)

**Cet exemple est fictif** : il illustre le fonctionnement du dépôt, pas un test réellement effectué ni des fichiers déjà produits dans ton atelier.

## D'abord : quel moteur IA pour ce projet ?

Cet atelier utilise **Qwen local et DeepSeek cloud comme deux moteurs complémentaires**, et pas seulement sept rôles distincts. **La route est un choix de confidentialité et de capacité avant d'être une question de spécialiste.**

Dans le scénario ci-dessous, deux variantes sont possibles :

| Variante | Comment le moteur est choisi | Conséquence |
|---|---|---|
| **Projet contenant des configurations privées** | **Qwen local**, sans accord cloud | Les sept rôles travaillent dans le périmètre local ; le travail complexe peut être découpé en tâches plus petites |
| **Démonstration sur une architecture et des fichiers fictifs/publics** | **DeepSeek V4.1 Flash**, après activation et **accord cloud de tout le projet** | Le même architecte, DevOps, rédacteur ou auditeur peut utiliser un contexte plus large et une capacité de raisonnement supérieure, avec facturation et contrôles |
| **Une seule question complexe dans le chat** | Tu choisis « · cloud (DeepSeek) » sur une nouvelle discussion autorisée | Tu utilises le moteur de capacité sans faire croire qu'un projet entier s'est routé tout seul |

**Attention :** le worker ne choisit pas automatiquement DeepSeek pour « DevOps » et Qwen pour « Rédacteur ». Un accord cloud de projet autorise les étapes concernées du projet ; il n'est **pas** une délégation automatique intelligente par rôle.

**Pourquoi choisir DeepSeek pour le scénario public ?** Parce que plusieurs modules d'infrastructure, des flux réseau, le pipeline, la sécurité et le rollback demandent un raisonnement transversal ; **le gain effectif par rapport à Qwen reste à mesurer** sur des cas réels.

→ [Stratégie de choix des moteurs](ARCHITECTURE_HYBRIDE.md).

## Le problème

Tu disposes d'une petite API qui doit tourner sur **une VM Rocky Linux**. Tu souhaites préparer une architecture compréhensible, un dépôt versionné, un pipeline GitHub Actions, les fichiers d'installation, les contrôles de sécurité et un runbook. Tu veux **comprendre le rôle de chaque fichier** avant de lancer quoi que ce soit.

### La demande initiale

> Prépare un projet de déploiement d'une API sur une VM Rocky Linux. Je maîtrise Linux et les services systemd, mais je découvre l'IaC et la CI/CD. Je veux un schéma de flux, un pipeline expliqué, des vérifications de sécurité, un rollback et un guide clair. Aucun déploiement sans mon accord.

**Pourquoi cette formulation fonctionne :** elle précise le système cible, tes acquis, les formats attendus, les conditions de réussite et surtout la limite « ne pas déployer ».

## Étape 1 — le mentor clarifie et propose un plan

**Rôle : Mentor infrastructure/OPS.**

Avant de produire du YAML au hasard, il doit identifier les inconnues importantes : comment construire l'application, où stocker son image, qui possède les secrets, quels ports sont nécessaires, comment observer la santé du service.

Il peut proposer un plan **court** comme celui-ci (exemple, non généré) :

| Tâche | Spécialiste | Résultat attendu | Critère de vérification |
|---|---|---|---|
| A. Définir les flux | **Architecte** | ADR + `.drawio` | Tous les échanges et secrets expliqués |
| B. Préparer la livraison | **DevOps** | Workflow CI, scripts et runbook | Syntaxe contrôlée, tests réels encore identifiés |
| C. Vérifier les risques | **Sécurité** | Rapport priorisé | Permissions et secrets relus, remédiations proposées |

Puis l'**auditeur** intervient sur les preuves et les livrables, selon la procédure du projet ; le **rédacteur** peut ensuite mettre en forme un guide si tu l'as demandé. L'**expert recherche** sert à documenter les versions actuelles, pas à encombrer chaque étape.

**Ce qui compte :** le modèle ne déclenche pas le plan tout seul. **Tu relis et approuves**, et c'est le **worker** qui répartit ensuite le travail.

## Étape 2 — l'architecte définit les flux

**Rôle : Architecte solutions.** Il reçoit les besoins, le plan validé et les sources permises.

```text
Développeur → dépôt GitHub → GitHub Actions (tests)
                                    ↓
                            image/version de l'API
                                    ↓
                         registre d'artefacts
                                    ↓
                         déploiement autorisé
                                    ↓
                         VM Rocky Linux / API
                                    ↓
                     journaux + contrôles de santé
```

L'architecte doit répondre à des questions très concrètes : d'où vient l'image, comment est-elle identifiée, comment le serveur l'obtient, quel compte a le droit de déployer, où se trouvent les secrets, quel est le chemin de retour arrière ?

Un **ADR** peut comparer un service systemd natif et un conteneur. Le schéma `.drawio` est **modifiable** : il ne constitue pas une ressource provisionnée.

**À relire :** identités, ports, chemins de données, sauvegarde et coût. Si l'architecture dépend de documentation récente, **Expert recherche** doit sourcer les faits.

## Étape 3 — le DevOps prépare des fichiers distincts

**Rôle : Ingénieur DevOps.** Il s'appuie sur les flux validés plutôt que de deviner. **Route :** Qwen pour une version locale privée, DeepSeek si le projet public a été autorisé au cloud. **Ses droits ne changent pas** avec le modèle utilisé.

Exemple de **structure souhaitée** (illustration, aucun fichier ci-dessous n'est déjà généré) :

```text
livraison/
├── README.md                    explication générale
├── .github/workflows/ci.yml     pipeline de vérification
├── infra/
│   ├── main.tf                  ressources déclaratives si nécessaires
│   ├── variables.tf             paramètres d'entrée
│   └── outputs.tf               sorties utiles
├── deploy/
│   ├── inventory.ini            hôtes Ansible si utilisés
│   └── deploy.yml               préparation/configuration
└── docs/
    ├── architecture.drawio      source du schéma
    ├── decisions.md             choix et hypothèses
    ├── runbook.md               procédures
    └── rollback.md              retour arrière
```

**Chaque maillon a son rôle**, et tous ne sont pas obligatoires :

| Maillon | Entrée → sortie | Pourquoi c'est important |
|---|---|---|
| **Git** | Fichiers versionnés → commit identifié | On sait quel changement on examine et comment revenir en arrière |
| **CI** | Commit → résultat des contrôles | On voit une erreur avant de livrer ; la CI doit elle-même être réellement exécutée |
| **Terraform** *(si nécessaire)* | Configuration + état → ressources prévues | `plan` présente des changements **à approuver** avant `apply` |
| **Ansible** *(si nécessaire)* | Inventaire + playbook → configuration attendue | L'idempotence ne se démontre pas avec une seule exécution |
| **Livraison/CD** | Artefact validé → service déployé | Les identités et les secrets ne doivent pas être en clair |
| **Exploitation** | Service en place → journaux, contrôles et rollback | Un workflow vert ne signifie pas automatiquement « service fonctionnel » |

L'agent peut **proposer** les commandes `terraform fmt`, `terraform validate`, `terraform plan`, `ansible-lint` ou `actionlint`. **Il ne les a pas exécutées.** Ses outils intégrés se limitent notamment aux vérifications statiques de certains formats, comme YAML/JSON/Python, ShellCheck et Markdown.

## Étape 4 — la sécurité examine les zones à risque

**Rôle : Ingénieur sécurité.**

Il devrait signaler par exemple :

- un jeton GitHub Actions avec des permissions trop larges ;
- un mot de passe ou une clé copiée dans un fichier de configuration ;
- un port de gestion exposé inutilement ;
- une image de conteneur référencée par un tag instable ;
- une stratégie de sauvegarde ou de retour arrière absente.

Pour chaque point, on attend **un constat, une preuve, un impact, une proposition et un test à faire**, pas « tout est sécurisé » sans démonstration.

Le modèle peut utiliser le lint/Gitleaks **sur du contenu autorisé**, mais **pas** lancer un audit réseau actif ou inspecter ton vrai PC.

## Étape 5 — le rédacteur rend le dossier compréhensible

**Rôle : Rédacteur pédagogique**, si le plan le prévoit.

Un bon runbook devrait répondre à cinq questions, dans cet ordre :

1. **Pourquoi ?** Le but du déploiement et les choix retenus.
2. **Avant ?** Les accès, versions, variables, secrets et sauvegardes nécessaires.
3. **Comment ?** L'ordre des commandes et les fichiers associés.
4. **Comment savoir ?** Résultats attendus, observabilité et diagnostics d'échec.
5. **Et si ça échoue ?** Conditions d'arrêt et procédure de rollback.

La **source Markdown** est modifiable ; les versions PDF/DOCX sont des exports. Une belle mise en page ne change pas le niveau de vérification des commandes.

## Étape 6 — l'auditeur compare preuves et exigences

**Rôle : Auditeur qualité**, dans une session différente de celle de l'auteur.

| Exigence | Une preuve suffisante serait… | Sans preuve |
|---|---|---|
| Le pipeline s'exécute | Un run GitHub Actions lié au bon commit | **Non vérifié**, même si le YAML est valide |
| Le service démarre | Un test réel sur la VM cible et son résultat | **Non vérifié**, même si le Dockerfile est correct |
| Le rollback fonctionne | Un essai de restauration daté et reproductible | **Non vérifié**, même si le runbook est détaillé |
| Les secrets sont protégés | Une vérification de la configuration et des droits | Risques résiduels à déclarer |
| Le dossier est utilisable | Formats attendus, liens et fichiers réellement accessibles | Retour à la tâche concernée |

L'auditeur doit signaler les écarts et demander une reprise. **C'est le même modèle que les autres rôles**, simplement dans un contexte séparé : le résultat mérite toujours une relecture humaine.

## Étape 7 — tu approuves la livraison

Le **projet central** conserve analyse, plan, fichiers collectés, preuves et rapport. Tu confirmes la livraison quand son contenu te convient. Cela **n'installe pas** l'API sur ta VM.

Si tu souhaites ensuite exécuter les commandes, fais-le sur ton laboratoire/ta VM, avec les accès et sauvegardes adéquats, puis **récupère des preuves réelles** pour une nouvelle revue.

## Faire ce parcours dans l'interface

Pour une **discussion simple**, ouvre Open WebUI sur `127.0.0.1:3000` et choisis le rôle adéquat. Pour le **projet complet**, utilise le tableau de bord `127.0.0.1:18890`, ou les commandes déterministes du chat : `!creer`, `!analyser`, `!planifier`, `!valider`, `!lancer`, `!auditer`, `!relire` et `!livrer`. Les confirmations fournies par le pont doivent être saisies **par toi**, dans les étapes appropriées.

Les raccourcis visuels Open WebUI **Voir les projets**, **État du projet** et **Commandes disponibles** sont uniquement **en lecture seule**. Ils ne peuvent pas approuver une livraison.

→ [Commandes et confirmations détaillées](fiches/03-discuter.md) · [Atelier Projets](fiches/04-atelier-projets.md).

## Pourquoi cet exemple est formateur

Il permet de séparer clairement **le besoin**, **l'architecture**, **l'automatisation**, **la sécurité**, **la pédagogie**, **la preuve** et **la décision humaine**. C'est précisément le réflexe utile en DevOps : ne pas confondre un fichier plausible avec un système réellement opérationnel.

[← Revenir au guide](GUIDE.md) · [Voir la carte des rôles](fiches/07-roles-et-outils.md)
