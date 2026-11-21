# Intégration GitHub opérationnelle — responsabilités, création et PR sous contrôle

[← Charte GitHub universelle](GITHUB_REPOSITORY_DESIGN_SYSTEM.md) · [Sources GitHub/Notion](INTEGRATION_GITHUB_NOTION.md) · [Charte wiki Notion](NOTION_WIKI_DESIGN_SYSTEM.md)

## Objectif et limites

L'atelier aide à produire **un dépôt GitHub réellement exploitable** :
présentation claire, choix techniques justifiés, installation, scripts et tests,
schémas Draw.io/SVG, sécurité, runbooks et preuves datées. Il organise le
travail des sept agents existants, mais l'approbation des publications et la
preuve d'exécution réelle appartiennent à l'utilisateur.

Cette étape apporte **trois commandes** :
- `clawfedora-github-scaffold` : générer un **squelette local** sans écraser un projet existant.
- `clawfedora-github-audit` : examiner localement un dépôt ou un snapshot en lecture seule.
- `clawfedora-github-pr` : préparer un plan local, puis, sur accord explicite,
  publier une **nouvelle branche et une pull request en brouillon** dans
  un dépôt distant **existant** ; jamais de push vers `main` et jamais de fusion.

**Non intégré :** création automatique du dépôt distant GitHub, modification
directe des paramètres de protection de branche, publication depuis le chat
OpenClaw sans intervention, réception du rendu navigateur, exécution sur la
machine Fedora de l'utilisateur. Une CI verte ne démontre aucun de ces points.

## 1. Qui est responsable de quoi ?

| Responsabilité | Responsable principal | Collaborateurs | Critère de sortie |
| --- | --- | --- | --- |
| Vision, périmètre et autorisations | **Chef des opérations** | Utilisateur | Plan, décisions et périmètre approuvés |
| Organisation des fichiers et architecture | **Architecte solutions** | Ingénieur DevOps | Arborescence utile, choix/ADR, flux et schémas justifiés |
| **Maintien du dépôt et intégration GitHub** | **Ingénieur DevOps — responsable GitHub** | Architecte, sécurité | Versionnement, branche, tests, PR et retour arrière maîtrisés |
| README, guides et qualité éditoriale | **Rédacteur — responsable documentation** | Architecte, DevOps | Navigation, explications, captures et liens exacts |
| Secrets, dépendances, permission et exposition | **Ingénieur sécurité** | DevOps | Risques et contrôles explicites |
| Versions et sources officielles | **Expert recherche** | DevOps | Références vérifiées |
| Revue indépendante avant publication | **Auditeur qualité** | Tous, sans auto-validation | Preuves, limites et écarts documentés |
| Publication, mise en public et fusion | **Utilisateur** | Chef | Accord explicite, puis revue humaine GitHub |

Pas de nouvel agent redondant à cette étape. Le rôle de **mainteneur GitHub** est
un mandat précis du DevOps actuel ; il n'est ni habilité à faire une fusion
automatique ni autorisé à remplacer la preuve personnelle de l'apprenant.

## 2. Nouvelle base de projet : préparation locale

```bash
# Aperçu local, aucune création :
clawfedora-github-scaffold \
  --name "MonProjet" --slug monprojet \
  --destination "$HOME/Projets/MonProjet"

# Après vérification et décision :
clawfedora-github-scaffold \
  --name "MonProjet" --slug monprojet \
  --destination "$HOME/Projets/MonProjet" \
  --apply --approve-name "MonProjet"
```

Le squelette contient README, STATUS, ROADMAP, guides d'installation,
architecture, exploitation, preuve, politique de sécurité, contribution et
modèles GitHub. Le générateur **ne crée ni source applicative ni licence ni
workflow CI ni capture fictive** : chaque projet doit ensuite faire ses vrais
choix. Le dossier de destination doit être vide ; un dépôt existant n'est jamais
écrasé.

Le dépôt distant n'est **pas créé** par ce mécanisme. Après revue des fichiers,
choisir une licence adaptée, créer séparément le dépôt GitHub avec la visibilité
souhaitée et vérifier ses réglages. Ne pas supposer qu'un dépôt doit être public.

## 3. Dépôt existant : réviser puis préparer une PR

1. Obtenir **un clone local de confiance** et identifier le SHA actuel de la
   branche par défaut ; ne pas confondre SHA Git et hash SHA-256 des fichiers.
2. Auditer le dépôt : `clawfedora-github-audit --path /chemin/du/clone`.
3. Les agents proposent des modifications ciblées et expliquées, conservées
   dans un **dossier de préparation séparé**, contenant seulement les
   fichiers explicitement à remplacer/ajouter et leurs chemins relatifs.
4. Le rédacteur et le DevOps relisent les documents/commandes ; sécurité vérifie
   l'absence de secrets ; auditeur contrôle les preuves et les sources.
5. Prévisualiser la publication **sans réseau ni token** :

```bash
clawfedora-github-pr \
  --repo "organisation/nom-du-depot" \
  --base main \
  --base-sha "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
  --branch "atelier/amelioration-documentation" \
  --changes "$HOME/Projets/proposition-github"
```

Le SHA d'exemple est un **placeholder à remplacer** par les 40 caractères de
la révision réelle. Le plan affiche noms, tailles et empreintes SHA-256 des
fichiers, pas leur contenu. Le responsable GitHub doit examiner les fichiers
locaux avant de demander l'accord ; le dossier de préparation ne doit pas
contenir de notes Notion privées.

## 4. Créer la PR brouillon uniquement sur approbation

**Préconditions :** un jeton GitHub finement limité au dépôt visé (opérations
sur le contenu et les PR selon la politique du compte), présent **dans
l'environnement local** via `GITHUB_TOKEN`. Ne jamais transmettre le token
dans le chat, dans une commande à arguments, dans Git ni dans un log.
La connexion GitHub de ChatGPT ne fournit **pas automatiquement** ce secret
au Fedora de l'utilisateur.

Préparer un fichier local de description de PR et inspecter le contenu du
dossier de changement. Reprendre le même plan en ajoutant les arguments :

```bash
clawfedora-github-pr \
  --repo "organisation/nom-du-depot" \
  --base main \
  --base-sha "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
  --branch "atelier/amelioration-documentation" \
  --changes "$HOME/Projets/proposition-github" \
  --title "Améliorer la documentation et les preuves" \
  --body-file "$HOME/Projets/proposition-pr.md" \
  --apply \
  --approve-repo "organisation/nom-du-depot"
```

**Important :** le jeton reste dans une variable d'environnement ; ne pas
l'écrire dans cette commande. Le mode `--apply` vérifie le dépôt, la branche
par défaut et son **SHA exact avant toute écriture**. Le code refuse une branche
qui n'utilise pas le préfixe `atelier/`. Il crée les blobs et **un seul commit**
au-dessus du SHA approuvé, une **branche nouvelle**, puis uniquement une
**draft PR**. Si GitHub ne confirme pas `draft: true`, la commande échoue.

Par défaut, les fichiers de `.github/workflows/` sont refusés : ils requièrent
en plus `--allow-workflows` et une revue des permissions, de l'exécution
GitHub Actions et des risques de fork. Toute permission supplémentaire
nécessite donc une décision explicite.

Le script n'exécute aucun fichier proposé ; les tests CI démarrent seulement
selon la configuration déjà présente du dépôt sur GitHub.

En cas d'échec d'une API après les écritures, un **blob, un commit ou une branche
peut subsister**. Inspecter GitHub avant de retenter ; l'outil ne supprime et
n'écrase jamais automatiquement des références distantes. Il ne modifie pas de
PR existante, ne rend pas publique une branche privée et ne fusionne pas.

## 5. Recette du dépôt professionnel

| Étape | Verdict acceptable |
| --- | --- |
| Architecture et rédaction | Source contrôlée, non « parfait » par défaut |
| Liens, schémas et templates | Contrôles statiques et graphiques distingués |
| Contrôles de code | Tests réellement exécutés, SHA et environnement |
| GitHub Actions | Workflows configurés, permissions et résultats réels |
| Sécurité et dépendances | Alertes documentées, pas « zéro risque » |
| PR | Brouillon, diff relu, CI et revue humaine |
| Fusion | **Action humaine distincte** |
| Déploiement sur Fedora / Rocky | Seulement après exécution et preuve sur machine |
| Visibilité du dépôt | Choix explicite, aucun changement automatique |

On vise un dépôt professionnel **par ses preuves et sa reproductibilité**,
pas par son nombre de fichiers. Le responsable GitHub garde les décisions,
les risques et les limitations accessibles et n'ouvre une nouvelle PR que
pour des modifications réellement justifiées.
