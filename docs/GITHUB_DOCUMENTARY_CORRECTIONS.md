# Préparer une correction documentaire GitHub — C02, lot 6

Avant de proposer un changement, rattacher chaque document à un constat
d'audit établi sur le SHA exact de la branche par défaut. L'aperçu est
local. L'opérateur utilise ensuite le
[circuit de publication en brouillon](GITHUB_PUBLICATION_WORKFLOW.md)
s'il approuve le diff et l'empreinte des fichiers.

## Préparer la revue

1. Produire l'[inventaire](GITHUB_DOCUMENTARY_INVENTORY.md) avec
   `--github PROPRIETAIRE/DEPOT` et le SHA complet de la base. Pour
   chaque audit que la proposition exploite, employer le même dépôt,
   le même SHA et la même empreinte d'inventaire.
2. Préparer les versions complètes corrigées des documents dans un
   dossier dédié, avec leurs chemins relatifs au dépôt. Le dossier
   contient uniquement les fichiers à remplacer. Les fichiers
   admissibles sont des documents Markdown `.md` existants à la racine
   ou sous `docs/`, en mode Git `100644`.
3. Indiquer les constats à l'aide de leur position dans le tableau
   JSON d'origine, comptée à partir de 1. Dans l'exemple, `links:1`
   désigne la première ligne de `findings` du rapport de liens.

| Famille | Tableau JSON | Constats utilisables |
| --- | --- | --- |
| [`links`](GITHUB_DOCUMENTARY_LINKS.md) | `findings` | Chemin ou ancre manquante, différence de casse, lien sortant de l'arbre. |
| [`coherence`](GITHUB_DOCUMENTARY_COHERENCE.md) | `checks` | Mention absente, cible technique absente, version divergente dans une déclaration. |
| [`ci`](GITHUB_DOCUMENTARY_CI.md) | `document_references` | Référence à un run rattaché à un autre SHA. Examiner si la référence est volontairement historique. |
| [`boundaries`](GITHUB_DOCUMENTARY_BOUNDARIES.md) | `findings` | Doublon, passage répété ou signal de diffusion localisé dans un document. |

```bash
python -m clawfedora.github_document_corrections \
  --repo PROPRIETAIRE/DEPOT --base main --base-sha SHA_COMPLET \
  --branch atelier/corriger-documentation --changes "$DOSSIER_PROPOSITION" \
  --inventory "$DOSSIER_PRIVE/inventaire.json" \
  --report "$DOSSIER_PRIVE/liens.json" --finding links:1 \
  --output "$DOSSIER_PRIVE/revue-corrections.json"
```

Répéter `--report` et `--finding` selon les besoins. Chaque rapport
fourni doit étayer au moins un constat sélectionné. Chaque constat
sélectionné doit concerner au moins un fichier à remplacer et chaque
fichier à remplacer doit avoir au moins un constat associé. Pour un
doublon, l'opérateur peut choisir le seul document à corriger.

La commande vérifie les empreintes des rapports et leur rattachement
au même arbre et au même dépôt. Ces empreintes vérifient l'intégrité
des entrées. Conserver les rapports originaux issus des commandes
d'audit et contrôler leur provenance. Toute version déjà présente
sur la base est refusée. Le rapport neuf est écrit en mode `0600`
hors Git et hors du dossier de proposition.

## Passer à la revue GitHub

Relire le diff local avec les constats originaux. Contrôler en
particulier l'exactitude de la correction et la diffusion du texte.
Le rapport privé contient les références des constats, les identifiants
Git des versions initiales et proposées, et l'aperçu exact du
publieur. Garder les rapports d'audit et de revue hors de la
description de PR.

Reprendre le même dépôt, la même base, le même SHA, la même branche et
le même dossier dans `clawfedora-github-pr`. Comparer son
`manifest_sha256` avec `publication_preview.manifest_sha256` dans
le rapport. Suivre ensuite la procédure d'approbation du publieur
pour créer le brouillon. Si les octets ou le SHA de base changent,
préparer une nouvelle revue.

La validation de l'effet de la correction passe par une nouvelle
exécution de l'audit concerné sur le SHA à vérifier. Le rapport de
préparation consigne les fichiers soumis à la revue et les
constats sélectionnés.
