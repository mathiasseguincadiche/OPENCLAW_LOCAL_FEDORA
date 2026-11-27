# Contrôle des liens documentaires GitHub — C02, lot 2

Le contrôle part d'un SHA Git complet. Il lit les blobs Markdown de cette
révision et compare leurs destinations à l'arbre du même commit. Les
fichiers non commités d'un clone ne changent pas les résultats.

```bash
python -m clawfedora.github_document_links --path /chemin/du/clone \
  --commit SHA_COMPLET --scope docs --scope README.md \
  --output "$DOSSIER_PRIVE/liens-github.json"
```

Utiliser `--github PROPRIETAIRE/DEPOT` à la place de `--path` pour lire
GitHub sur ce SHA. Dans un clone, `--repository PROPRIETAIRE/DEPOT`
permet de reconnaître les liens absolus vers ce même dépôt. Le rapport
contient l'empreinte de l'inventaire. Pour reprendre une vérification
existante à la même source, passer cette valeur avec `--inventory-sha256`.

`--scope` peut désigner un document ou un dossier versionné. Par défaut,
le contrôle examine tous les Markdown admissibles. Une ancre peut viser
un document hors du périmètre sélectionné, mais toujours dans le même
arbre Git.

| Résultat | Interprétation |
| --- | --- |
| `valid_path`, `valid_anchor` | Le chemin ou l'ancre Markdown est présent dans la révision. |
| `missing_path`, `path_case_mismatch`, `outside_repository` | La destination manque, utilise une casse divergente ou sort de l'arbre. |
| `missing_anchor` | Le titre ou l'ancre nommée n'a pas été retrouvé dans le Markdown lu. |
| `target_excluded`, `target_content_not_checked`, `fragment_not_checked` | L'outil ne peut pas vérifier cette destination au niveau demandé. |
| `external_not_checked`, `other_revision_not_checked` | Le lien est hors révision ou hors dépôt. |

La lecture reconnaît les liens et images Markdown, les définitions de
référence, les liens HTML simples, les ancres de titre et les ancres
`<a name="…">`. Les constats indiquent la ligne de début du bloc Markdown.
Les fragments de lignes de code et le rendu GitHub demandent une
vérification dédiée. Les URL externes, leurs paramètres et les chemins
exclus ne sont pas reproduits dans le rapport. Le contrôle ne suit aucun
lien.

La commande écrit un fichier privé neuf hors Git et renvoie `1` si elle
signale un lien cassé, `2` si elle refuse de produire le rapport et `0`
sinon. Le rapport expose les fichiers examinés et ceux dont le Markdown
n'a pas pu être lu dans les limites de taille ou de format. Si un budget
global est dépassé, relancer avec un périmètre plus petit.

[Syntaxe des liens et ancres GitHub](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax)

[Comparer les déclarations documentaires aux sources techniques](GITHUB_DOCUMENTARY_COHERENCE.md).
