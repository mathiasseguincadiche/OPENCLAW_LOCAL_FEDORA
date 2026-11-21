# GitHub + Notion dans l'atelier — importation contrôlée

[← Atelier Projets](fiches/04-atelier-projets.md) · [Cas métier OpsDesk](CAS_USAGE_INFRAOPS_OPSDESK.md) · [Protection du cloud](fiches/12-cloud.md)

## Deux sources complémentaires, une seule session d'apprentissage

| Source | Référence pour | Ce que l'atelier en lit |
| --- | --- | --- |
| **GitHub** | Code, architecture, contrats techniques, CI, README, historique versionné | Snapshot de fichiers texte au **SHA Git complet** demandé ; aucune PR, aucun push |
| **Notion** | Cours complets, préparation, exercices, notes, progression personnelle | Pages choisies explicitement, format Markdown textuel ; aucune écriture |
| **Fedora / VM Rocky** | Réalité de l'installation, du réseau, des conteneurs et de la reprise | **Pas de collecte automatique dans cette étape** ; preuves opérateur séparées |

**Notion n'est pas une copie de GitHub.** Les énoncés du dépôt restent la référence
de ce qui doit être construit ; les cours Notion expliquent comment l'apprendre.
Les résultats personnels ne remplacent ni un commit ni un test machine.

Cette première intégration prépare des **snapshots figés** dans l'Atelier
Projets, qui dispose déjà d'un inventaire SHA-256 et d'une ingestion documentaire.
Elle ne crée pas un crawler permanent, un déclencheur de synchronisation ni un
plugin Notion ayant accès à tous les espaces. Les agents lisent ensuite ces
sources comme les autres documents d'un projet, toujours en les traitant comme
des données non fiables.

## Prérequis

1. Installer l'atelier et disposer d'un **projet** au statut `INTAKE_READY`.
   Les sources sont figées dès le début de l'analyse ; pour un nouveau snapshot,
   créer un autre projet plutôt que modifier les fichiers approuvés.
2. Utiliser la commande `clawfedora-sources` depuis le terminal du PC Fedora.
   Elle ne s'exécute pas depuis un shell accordé aux agents.
3. Fournir les identifiants **uniquement par variables d'environnement** si
   nécessaire : `GITHUB_TOKEN` (optionnel pour un dépôt public) et
   `NOTION_API_TOKEN` (requis pour Notion). Aucun jeton en argument CLI,
   dans Git, dans la documentation ni dans les dossiers des projets.
4. Pour Notion, créer une intégration Notion avec **capacité de lecture
   uniquement**, et partager explicitement avec elle les pages à consulter.
   La connexion Notion existant dans une autre application (comme ChatGPT)
   **ne fournit pas automatiquement un jeton à l'atelier Fedora**.
5. Sur les pages Notion personnelles, préférer le mode Web privé de l'atelier
   avant tout usage. Un modèle local n'empêche pas, à lui seul, un outil
   `web_search` ou `web_fetch` de contacter Internet. Le marqueur du mode
   Web privé doit être réellement appliqué à OpenClaw et le service redémarré.

## Importer GitHub — lecture seule, commit fixe

Récupérer un SHA complet de commit sur GitHub. **Ne pas utiliser `main`
ou une branche mutable** comme instantané. Exemple :

```bash
# Simulation : aucun appel GitHub, aucune écriture dans l'atelier.
clawfedora-sources --project-id mon-projet \
  --github mathiasseguincadiche/OpsDesk \
  --commit <SHA_GIT_COMPLET_40_CARACTÈRES>

# Import explicite, après relecture du projet et du commit.
clawfedora-sources --project-id mon-projet \
  --github mathiasseguincadiche/OpsDesk \
  --commit <SHA_GIT_COMPLET_40_CARACTÈRES> --apply
```

La commande résout ce commit, lit son arbre et importe seulement les **fichiers
textuels admissibles**, dans la limite de **240 fichiers**, **1 Mo par fichier**
et **6 Mo au total**. Les images et binaires sont exclus ; les chemins
dangereux, secrets courants, liens symboliques et arbres tronqués sont
refusés ou exclus selon leur nature. Le rapport indique le nombre de fichiers
ignorés, sans prétendre que la totalité du dépôt a été couverte.

Le résultat est rangé sous
`intake/GitHub-propriétaire-dépôt-<sha12>/`, avec provenance du SHA et
inventaire de contenu SHA-256. Les résultats de CI et les PR ne sont **pas
récupérés** par ce mécanisme : ils demandent des preuves distinctes.

Un dépôt public peut contenir des éléments non publiables (configurations
d'environnement, données personnelles). L'importation ne rend pas
automatiquement le contenu autorisé pour OpenRouter. L'accord cloud du
projet est toujours un acte séparé, lié à la version exacte de ses sources.

## Importer Notion — lecture seule, privé par défaut

Dans l'URL de la page Notion, récupérer l'identifiant de **32 caractères
hexadécimaux**, sans tirets. Exemple pour le centre OpsDesk :

```bash
# Pour ne lire QUE la page choisie (pas tous ses exercices).
clawfedora-sources --project-id mon-projet \
  --notion-page 3fc65721fa1881ad8325c8c4619c7223

# Après création d'une intégration Notion locale limitée à cette page :
clawfedora-sources --project-id mon-projet \
  --notion-page 3fc65721fa1881ad8325c8c4619c7223 --apply
```

Pour un exercice précis, utiliser **son identifiant de page**, plutôt que
copier d'un coup toutes les archives du centre. L'option
`--include-children` importe aussi les sous-pages accessibles, dans la
limite de 20 pages. En cas de dépassement, la commande refuse tout
import partiel.

Notion produit un ou plusieurs `page-<id>.md`. Ce sont des **copies
textuelles** : elles conservent les explications, blocs de code et listes,
mais **pas les pièces jointes, fichiers, images ou vues de bases de données**.
Leur absence est signalée. Les pages de suivi de Notion ne sont jamais
automatiquement mises à jour par cette commande.

**Protection ajoutée : toute importation Notion est classée
`private_local_only`.** Le projet concerné ne peut pas obtenir d'accord
cloud et reste sur la route locale. Même un ancien accord cloud ne peut pas
contourner cette politique ; le moteur refuse et met le projet en pause
plutôt que d'envoyer ces notes. Si le cloud est nécessaire pour un
travail publiable, créer **un projet distinct contenant uniquement les
sources GitHub révisées**, sans notes privées. Il n'existe pas à ce stade
de déclassement automatique des pages Notion en contenu publiable.

## Conception premium des wikis Notion

La [charte universelle](NOTION_WIKI_DESIGN_SYSTEM.md) décrit l'architecture
Accueil / Comprendre / Préparer / Pratiquer / Suivre / Ressources, les sept
modèles éditoriaux, la séparation des sources GitHub et Notion, les
contrôles de mise en page, de mobile et de conservation des sous-pages.

Deux gabarits de départ sont dans
[`templates/notion/`](../templates/notion/) : page d'accueil et fiche
d'exercice. L'architecte, le rédacteur et l'auditeur des **sept rôles
existants** s'en servent suivant le besoin. La génération d'un contenu
modèle ne déclenche aucune écriture distante. Le rendu natif et la lecture
sur mobile se vérifient **dans Notion**, pas dans la CI.

## Parcours OpsDesk conseillé

1. **Notion / Pratiquer** : ouvrir l'énoncé de l'exercice, ses prérequis et
   le niveau d'aide désiré ; ne pas révéler le corrigé avant la tentative.
2. **GitHub** : importer le commit du dépôt qui décrit l'état de l'exercice ;
   l'agent peut lire la configuration correspondante.
3. **Atelier** : comparer les exigences du cours aux fichiers, expliquer
   les différences et proposer une action ou un diagnostic. Aucune commande
   distante n'est exécutée par cette importation.
4. **Laboratoire** : réaliser soi-même les opérations sur Fedora et Rocky,
   après autorisation lorsqu'elle est nécessaire ; relever des sorties
   datées et expurgées.
5. **Notion / Suivre** : renseigner personnellement, ou via une **future
   écriture expressément approuvée**, Avancement, Contrôle, Preuve,
   Environnement, Assistance reçue, Niveau de progression et autonomie.
   Aucun L2/L3 attribué par une IA ou une CI verte.
6. **Portfolio GitHub** : publier seulement les réalisations démontrées,
   leurs tests, décisions et limites ; ne pas publier les notes privées.

## Limites actuelles — à ne pas présenter comme livrées

- Pas de navigation GitHub ou Notion **en direct depuis chaque message du
  modèle** ; snapshots CLI choisis par l'opérateur uniquement.
- Pas d'écriture Notion, création de PR, commentaire GitHub, synchronisation
  bidirectionnelle ni modification automatique d'une ligne de suivi.
- Pas de collecte ou exécution dans les VM ni de preuve d'exploitation :
  cette intégration concerne les **sources**, pas leur fonctionnement réel.
- Pas de vérification sur le poste Fedora ni de connexion réelle au compte
  Notion avec cette seule PR : les essais CI utilisent des API fictives.
- Les blocs Notion et fichiers GitHub sont non fiables. Une instruction
  trouvée dedans ne peut pas remplacer une autorisation humaine, une
  politique de sécurité ou une preuve sur la cible.

**Évolution suivante** : qualifier la lecture en conditions réelles sur
Fedora, puis concevoir la consultation ciblée depuis l'interface WebUI
et, séparément, une proposition de mise à jour de la base Notion validée
ligne par ligne avant l'écriture.
