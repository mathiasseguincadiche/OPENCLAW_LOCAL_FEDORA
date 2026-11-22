# Recherche locale de preuves — plusieurs documents, pas un seul extrait

[← Guide](GUIDE.md) · [Architecture](fiches/11-comment-ca-marche.md) · [Qualité](archives/2026/PLAN_QUALITE_2026.md)

## Pourquoi changer la recherche ?

Sur un dépôt Terraform/Ansible multi-fichiers, les quatre extraits les mieux
classés par BM25 peuvent provenir **du même fichier**. Un agent risque alors
d'ignorer un second document pourtant lié à la question, simplement parce
que le premier répète plus souvent les termes recherchés.

Le moteur local `clawfedora.knowledge.search` utilise **SQLite FTS5**
sur la machine de l'utilisateur ; il ne requiert **aucune API, aucun modèle
d'embedding, aucun service cloud**.

## Nouvelle sélection à sources diversifiées

1. La requête est bornée et transformée en mots simples (pas de SQL utilisateur).
2. SQLite classe un **ensemble borné** d'extraits par BM25, chemin, page et ligne.
3. Tant que possible, la sélection conserve **le meilleur extrait de chaque
   document distinct**, avant de compléter les places restantes avec les autres
   passages les mieux classés.
4. Les limites historiques sont conservées : **quatre extraits maximum et
   4 000 caractères au total** suivant `knowledge_policy.yaml`.
5. Chaque extrait conserve son **vrai chemin, page, ligne et métadonnées** ;
   une note de recherche périmée reste marquée comme telle.

Par exemple, si les fichiers `module.tf` et `playbook.yml` contiennent
des éléments pertinents, le résultat cherche à faire apparaître **les deux**
dans le contexte, plutôt que quatre passages du module Terraform.

## Recherche croisée avec le dernier snapshot GitHub approuvé

Pour les projets longs, un import GitHub initial peut devenir obsolète après
l'enregistrement d'un nouveau commit via
[`clawfedora-github-refresh`](GITHUB_SNAPSHOT_REFRESH.md).

Le moteur local distingue maintenant :
- les sources documentaires **initiales** de l'index FTS5 (dont les
  pages Notion importées en privé et les décisions datées) ;
- les fichiers textuels de la **dernière révision GitHub vérifiée**,
  conservés avec leurs SHA complets et leurs empreintes.

La recherche croisée `clawfedora.project_retrieval.retrieve` lit le
snapshot **déjà téléchargé et approuvé**, sans appel réseau et sans modifier
l'index FTS5, les tâches ou les pages Notion. Une version GitHub remplacée
ne consomme plus de place parmi les résultats : l'exclusion intervient
**avant** la sélection des meilleurs extraits FTS5. Cela évite que plusieurs
extraits du vieux code masquent une documentation Notion encore pertinente.

Les quatre résultats maximum privilégient des **fichiers distincts**
et conservent leurs chemins, lignes, empreintes, provenance et SHA GitHub.
La limite globale reste de 4 000 caractères, et chaque extrait est réduit
à 700 caractères dans ce mode pour rendre visibles plusieurs sources.

### Utilisation

~~~bash
# Recherche locale : aucune synchronisation distante, aucune opération cloud.
clawfedora-source-search --project-id opsdesk \
  --query "Terraform Ansible configuration réseau"

# Rechercher uniquement dans l'index de départ, sans révision GitHub.
clawfedora-source-search --project-id opsdesk \
  --query "ancien état du projet" --initial-only
~~~

Dans **Open WebUI**, un chat ClawFedora **local** sélectionné reçoit aussi
ces passages croisés avec sa réponse pédagogique. Les modèles cloud ne
reçoivent **pas** les nouvelles révisions GitHub via cette fonction, même si
le chat dispose d'un autre consentement. Les protections préexistantes
interdisent tout projet contenant des snapshots Notion privés au cloud.

Il n'y a **aucune recherche transversale entre plusieurs projets** :
un projet GitHub public et un projet Notion privé séparés ne sont pas
fusionnés en coulisse. Pour croiser leurs sources, elles doivent avoir été
importées explicitement dans **le même projet local**, dans le respect de
la politique de sources figées à l'entrée. Aucun connecteur Notion ou
GitHub n'est interrogé lors d'une question.

Un extrait trouvé est une piste documentaire, **pas une exécution Terraform,
une CI vérifiée ou une preuve de compétence**. Les tests vérifient sur
corpus synthétiques les références, la séparation cloud et le signalement
de la corruption ; la pertinence pédagogique finale sur OpsDesk est à
qualifier sur une véritable installation Fedora.

### Recette de qualification reproductible

La commande `clawfedora-retrieval-acceptance` mesure, sur un corpus de questions
adaptées au projet, la couverture documentaire, la diversité des fichiers,
la stabilité des citations et le respect de la version GitHub courante.
Elle ne publie pas les extraits privés et ne modifie pas l'index local.

Voir la [procédure de qualification sous Fedora](QUALIFICATION_RECHERCHE_LOCALE.md)
et son [fichier de scénarios personnalisable](exemples/recette-recherche-opsdesk.example.json).
Une CI verte ne remplace pas l'observation sur la machine Fedora.

## Ce que la recherche ne prouve pas

- Une correspondance textuelle n'est **pas** une validation du sens ou de
  la justesse des documents ;
- l'index ne garantit pas de lire **toutes** les sources utiles (documents
  limités, formats pris en charge, PDF textuels jusqu'à 20 pages) ;
- le nombre de candidats est borné (au plus 128) ; un document très mal classé
  peut donc rester absent malgré la diversification ;
- aucune affirmation de l'agent ne devient une preuve de CI, un test Terraform
  ou un déploiement réel ;
- **la recherche reste sur le PC** ; choisir ensuite DeepSeek pour discuter
  de sources privées demeure interdit sans accord clair et approprié.

## Portée pour les explications pédagogiques

La recherche SQLite FTS5 fournit **jusqu'à quatre passages et 4 000 caractères au total**, avec chemins, pages et lignes. Elle aide à retrouver une preuve dans les documents d'un projet ; elle ne constitue ni une mémoire automatique de conversation ni une recherche sémantique garantie. Pour continuer d'une séance à l'autre, l'utilisateur enregistre **volontairement** les acquis utiles dans sa [fiche mentor](fiches/05-apprendre.md), sans envoyer le contenu privé au cloud par défaut. Pour une revue d'exactitude, confronter les citations aux sources et ne pas confondre un extrait trouvé avec un test technique.

## Comment qualifier la pertinence, à la fin

Préparer plusieurs mini-corpus synthétiques avec une question attendue,
des documents pertinents et du bruit répétitif. Mesurer : couverture des
sources pertinentes dans les quatre résultats, justesse des chemins/pages,
taux de citations réellement correspondantes, stabilité après réindexation,
latence et taille de contexte.

La CI ne vérifie aujourd'hui que des corpus de tests synthétiques et le
respect des limites. Ce n'est **pas encore un benchmark de réponse Qwen/DeepSeek**.
