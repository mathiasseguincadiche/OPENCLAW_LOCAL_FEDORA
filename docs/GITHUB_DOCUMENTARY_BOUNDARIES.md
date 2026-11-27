# Doublons et frontières documentaires GitHub — C02, lot 5

L'audit travaille sur les chemins d'un commit exact. L'opérateur désigne
le périmètre destiné au public. Le rapport d'audit reste privé.

```bash
python -m clawfedora.github_document_boundaries --path /chemin/du/clone \
  --commit SHA_COMPLET --public-scope README.md --public-scope docs \
  --private-policy "$DOSSIER_PRIVE/frontiere.json" \
  --output "$DOSSIER_PRIVE/frontiere-audit.json"
```

Utiliser `--github PROPRIETAIRE/DEPOT` pour lire le même commit via
GitHub. Dans un clone, `--repository PROPRIETAIRE/DEPOT` permet de
reconnaître les liens absolus vers le même commit. Utiliser
`--public-tree` uniquement si l'arbre entier constitue le périmètre
destiné au public. `--inventory-sha256` vérifie le lien avec
l'[inventaire Git](GITHUB_DOCUMENTARY_INVENTORY.md) de la même source.

## Politique privée facultative

Le fichier JSON opérateur contient `schema: 1`, `private_paths`
(chemins relatifs de fichiers ou dossiers) et `literals` (chaînes de
12 à 512 caractères). Le fichier doit être privé, en mode `0600`
hors Git. Aucun littéral n'est envoyé au service GitHub. Les chemins
déjà exclus par l'inventaire restent protégés, même en l'absence
d'une politique additionnelle.

| Signal du rapport | Lecture |
| --- | --- |
| `identical_documents` | Identifiants Git des blobs identiques dans plusieurs documents du périmètre. |
| `repeated_normalized_passage` | Passage de prose d'au moins 120 caractères et 18 mots, présent dans plusieurs documents après normalisation. |
| `restricted_paths_in_public_scope` | Nombre de chemins protégés suivis dans le périmètre déclaré public. |
| `public_blob_matches_private_path` | Un document éligible et un chemin protégé pointent vers les mêmes octets selon Git. Le blob n'est pas lu. |
| `restricted_target_reference` | Lien interne vers un chemin exclu, un lien symbolique ou un sous-module. Le rapport conserve uniquement le document source et la ligne. |
| `private_literal_in_public_document` | Correspondance littérale dans un document éligible, signalée par ligne et position de la règle opérateur. |

Les doublons sont des éléments à relire. Les archives et gabarits sont
signalés lorsqu'ils sont reconnaissables par leur dossier. Le rapport
donne sa couverture, notamment les documents omis ou non lus. Il ne
contient ni passages, ni littéraux, ni chemins privés. Les liens
externes et les autres révisions ne sont pas interrogés. Les permissions
réelles, l'historique Git et une recherche générale de secrets sont
hors du périmètre.

Le rapport neuf est écrit hors Git en mode `0600`. La commande
renvoie `1` si des constats demandent une revue, `0` si aucun constat
n'est signalé et `2` en cas de refus.
