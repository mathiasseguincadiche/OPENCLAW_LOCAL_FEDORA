# Recherche locale de preuves — plusieurs documents, pas un seul extrait

[← Guide](GUIDE.md) · [Architecture](fiches/11-comment-ca-marche.md) · [Qualité](PLAN_QUALITE_2026.md)

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

## Comment qualifier la pertinence, à la fin

Préparer plusieurs mini-corpus synthétiques avec une question attendue,
des documents pertinents et du bruit répétitif. Mesurer : couverture des
sources pertinentes dans les quatre résultats, justesse des chemins/pages,
taux de citations réellement correspondantes, stabilité après réindexation,
latence et taille de contexte.

La CI ne vérifie aujourd'hui que des corpus de tests synthétiques et le
respect des limites. Ce n'est **pas encore un benchmark de réponse Qwen/DeepSeek**.
