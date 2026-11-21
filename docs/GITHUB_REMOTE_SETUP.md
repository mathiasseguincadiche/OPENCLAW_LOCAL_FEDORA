# GitHub distant — création et protections sous approbation

[← Workflow GitHub](GITHUB_PUBLICATION_WORKFLOW.md) · [Charte de qualité](GITHUB_REPOSITORY_DESIGN_SYSTEM.md) · [Intégration GitHub/Notion](INTEGRATION_GITHUB_NOTION.md)

## Portée exacte

`clawfedora-github-remote` complète le générateur local et la publication de PR de l'atelier :

- **Créer un dépôt personnel GitHub** privé par défaut, avec README initial et issues activées ;
- **Auditer en lecture seule** les paramètres du dépôt, les rulesets visibles et les permissions par défaut des workflows ;
- **Proposer puis créer**, après approbation explicite, un ruleset pour exiger une PR sur la branche principale, interdire sa suppression et les pushes non fast-forward ;
- **Proposer puis réduire** les droits GitHub Actions par défaut à `read`, sans approbation de PR par le jeton Actions.

Ce module **ne gère pas les organisations**, ne fusionne aucune PR, ne change pas la visibilité d'un dépôt existant et n'applique aucune politique sans accord sur une empreinte de plan. Les plans sont calculés **hors ligne**, sans jeton ni accès Internet.

Les disponibilités des rulesets, protections et options Actions peuvent varier selon le type de compte, l'offre GitHub et les permissions. Un refus HTTP ne prouve pas qu'une protection est désactivée.

## 1. Créer un dépôt privé

```bash
# Aperçu sans réseau, privé par défaut :
clawfedora-github-remote create \
  --name "MonProjet" \
  --description "Laboratoire InfraOps reproductible"

# Quand le plan est relu et son manifest_sha256 relevé :
clawfedora-github-remote create \
  --name "MonProjet" \
  --description "Laboratoire InfraOps reproductible" \
  --apply \
  --approve-name "MonProjet" \
  --approve-manifest "REMPLACER_PAR_64_CARACTERES_HEXA"
```

La première requête d'écriture crée un dépôt **privé**, initialisé par
GitHub avec un README minimal. Les véritables fichiers du projet sont ensuite
proposés **dans une PR brouillon**, jamais copiés aveuglément sur `main`.
Le script vérifie que l'identité du propriétaire et la visibilité du dépôt
renvoyées par GitHub correspondent aux valeurs demandées.

La création d'un dépôt **public** est également possible, mais jamais
par défaut : `--visibility public` est nécessaire dans l'aperçu et
l'exécution, accompagné de `--approve-public`. Le README minimal devient
alors visible immédiatement ; choisir ce mode uniquement après vérification
des données, du nom, de la licence et de la provenance.

**Jeton :** conserver `GITHUB_TOKEN` exclusivement dans l'environnement
du processus local et dans un coffre/gestionnaire de secrets adapté ;
ne jamais le placer en argument de ligne de commande, fichier `.env`,
journal de CI, réponse IA ou espace Notion.
La création de dépôt nécessite les permissions GitHub de **Repository
creation** ou **Administration** applicables au type de jeton choisi.
Les permissions de gestion des règles et de contenu/PR sont des capacités
distinctes à accorder au strict nécessaire. <https://docs.github.com/en/rest/repos/repos>

## 2. Auditer les protections existantes

```bash
clawfedora-github-remote audit --repo "compte/MonProjet"
```

Le rapport inspecte les métadonnées du dépôt, la liste visible de rulesets
et les permissions Actions. Les valeurs `NOT_EVALUATED` indiquent un contrôle
impossible ou interdit, **pas** un statut sûr ou non sûr. Voir dans GitHub :
**Settings → Rules / Branches** et **Settings → Actions → General**.

L'audit n'a pas la capacité de mesurer le rendu graphique du README ni
d'attester une exécution réelle des tests sur le poste Fedora.

## 3. Protéger la branche principale via ruleset

```bash
# Plan : exiger une PR, interdire les suppressions et les force-pushes.
clawfedora-github-remote policy \
  --repo "compte/MonProjet" --branch main --kind pr-ruleset

# Accord réservé à la version exacte du plan :
clawfedora-github-remote policy \
  --repo "compte/MonProjet" --branch main --kind pr-ruleset \
  --apply --approve-repo "compte/MonProjet" \
  --approve-manifest "REMPLACER_PAR_EMPREINTE_DU_PLAN"
```

Ce ruleset **n'impose pas** un check CI de nom inconnu. Quand les workflows
du projet existent et sont verts, ajouter séparément leurs vrais noms
comme contrôles obligatoires, en inspectant le rendu GitHub et les éventuels
bypass. Un ruleset déjà créé par l'atelier n'est pas modifié silencieusement ;
le module refuse les doublons.

Le nombre d'approbations de revue demandé dans le modèle est **zéro** : un
dépôt personnel ne peut pas nécessiter mécaniquement une revue tierce qui
n'existe pas. L'atelier impose tout de même l'approbation de son auteur
avant toute fusion, mais ce contrôle de procédure n'est pas équivalent
à une exigence de revue serveur.

**Après création** : ouvrir les paramètres GitHub, vérifier que le ruleset
s'applique bien à `main` et que la plateforme le fait réellement respecter.
L'API peut refuser sa création sur un dépôt privé selon l'offre.

## 4. Restreindre les autorisations des workflows

```bash
clawfedora-github-remote policy \
  --repo "compte/MonProjet" --branch main --kind workflow-readonly

# Après accord sur la bonne empreinte :
clawfedora-github-remote policy \
  --repo "compte/MonProjet" --branch main --kind workflow-readonly \
  --apply --approve-repo "compte/MonProjet" \
  --approve-manifest "REMPLACER_PAR_EMPREINTE_DU_PLAN"
```

Le changement n'est déclaré **vérifié** que si une lecture API après la
modification confirme `default_workflow_permissions=read` et
`can_approve_pull_request_reviews=false`. Les workflows qui publient
des artefacts doivent demander explicitement leurs permissions minimales
et être examinés indépendamment.

## 5. Processus complet sous contrôle

1. Décrire le projet dans l'atelier et faire valider le périmètre par le chef.
2. Obtenir la structure du dépôt local avec `clawfedora-github-scaffold`.
3. Faire produire/revoir le vrai code, l'architecture, le README, les procédures
   d'installation et les tests selon les rôles existants.
4. Créer le dépôt GitHub privé **si nécessaire**, sur approbation.
5. Vérifier son `main`, sa visibilité et ses paramètres ; appliquer
   éventuellement les protections sous approbation distincte.
6. Auditer les fichiers locaux avec `clawfedora-github-audit`.
7. Prévisualiser les changements avec `clawfedora-github-pr` :
   `repo`, SHA de base, `manifest_sha256`, fichier de description de PR.
8. Une fois autorisée, créer la PR **brouillon** et examiner le diff, la CI
   et les captures réelles (clair/sombre/mobile).
9. L'utilisateur reste responsable de déclarer la PR prête et de la fusionner.

Le [panneau local GitHub et les commandes Open WebUI](GITHUB_CHAT_DASHBOARD.md)
permettent également de préparer et de contrôler les opérations par une
interface dédiée. Les commandes de publication ne sont jamais appelées
par le modèle lui-même.

## 6. Limites des validations

- Tests unitaires/CI sur runner ≠ essais sur le poste Fedora ni avec les
  droits réels GitHub du propriétaire.
- Un ruleset listé ≠ protection effectivement active.
- Une image SVG valide ≠ diagramme lisible dans un navigateur.
- Une PR brouillon créée ≠ changement publié sur `main`.
- Le travail pédagogique personnel demeure à exécuter et démontrer.
