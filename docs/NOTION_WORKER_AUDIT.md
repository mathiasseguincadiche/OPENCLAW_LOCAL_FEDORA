# Audits Notion dans le worker — lot 8

Le worker peut faire examiner un inventaire Notion déjà capturé, comparer
deux états et produire les preuves des doublons, références et sources de
vérité. Les rôles de préparation peuvent également générer un
[plan de rationalisation](NOTION_RATIONALIZATION.md).

| Rôle | Opérations dans une tâche locale approuvée |
| --- | --- |
| Chef des opérations, architecte solutions, rédacteur pédagogique | `inventory`, `compare`, `duplicates`, `references`, `sources`, `plan` |
| Auditeur qualité | `inventory`, `compare`, `duplicates`, `references`, `sources` |

Les calculs reposent sur les fichiers fournis par l'opérateur. Le contrôle
du worker ne contacte aucun service et le rapport porte le statut
`REVIEW_REQUIRED`.

## Autoriser une tâche

Sélectionner un projet assigné, l'identifiant réel d'une tâche et la page
racine de la capture. Utiliser les fichiers JSON privés des lots précédents.

```bash
python -m clawfedora.notion_worker_audit --runtime "$RUNTIME" approve \
  --project ID_PROJET --task ID_TACHE --page ID_WIKI \
  --inventory "$DOSSIER_PRIVE/inventaire.json" \
  --operation duplicates --operation plan
```

`--before` fournit l'état de comparaison. `--reference-capture` permet
de réutiliser son inventaire et les références. `--annotations`,
`--registry`, `--observations` et `--as-of` restent facultatifs selon
l'opération. La commande valide le périmètre des entrées et en conserve
une copie privée avec leurs empreintes et celle de la tâche. Pour
remplacer cette autorisation, fournir `--replace-sha256` avec l'empreinte
actuelle. L'opération se fait sous le verrou du worker. Si la définition de
la tâche a changé, revoir les entrées et renouveler l'autorisation.

Le worker inscrit uniquement l'empreinte et les opérations approuvées
dans le snapshot de la tâche locale. L'appel utilise le rôle assigné et
le périmètre de la session active. Les fichiers de preuve complets restent
dans l'état privé du runtime. Le modèle reçoit un résumé limité à des
comptages et des empreintes. Le collecteur vérifie le rapport avant
de ranger le reçu de l'outil dans les preuves de la tâche.

## Relire le rapport

Le reçu collecté contient le périmètre `projects/ID_PROJET/ID_TACHE/SESSION`,
l'opération et `artifact_sha256`. Sur le poste local, vérifier le rapport
avec ces valeurs.

```bash
python -m clawfedora.notion_worker_audit --runtime "$RUNTIME" verify \
  --project ID_PROJET --task ID_TACHE --session SESSION \
  --operation plan --sha256 EMPREINTE_DU_RAPPORT
```

Ouvrir le fichier JSON privé indiqué par la commande et relire les preuves,
les limites de couverture et les protections. Le reçu établit le résultat
du calcul pour la tâche. La validation humaine du constat et l'approbation
d'une éventuelle édition passent par le
[workflow Notion contrôlé](NOTION_CONTROLLED_WRITES.md). Les préconditions
de ce workflow s'appliquent à toute écriture. Les tests du worker utilisent
des captures synthétiques. La recette Atlas et les essais natifs sur Fedora
restent à effectuer.
