# Contrôle des liens et références Notion — lot 5

La capture réutilise le parcours natif de la [page racine autorisée](NOTION_NATIVE_INVENTORY.md).
Elle conserve les identifiants des sources, les destinations Notion reconnues,
les empreintes des URL externes ordinaires et l'échéance des fichiers
temporaires. Elle n'enregistre ni textes, ni URL, ni paramètres.
Le rapport se produit ensuite hors ligne, à partir de cette capture.

## Capturer puis contrôler

```bash
install -d -m 700 "$HOME/.local/state/clawfedora-notion"

# Lecture de la structure Notion avec la connexion opérateur existante.
python -m clawfedora.notion_references capture --page ID_WIKI \
  --output "$HOME/.local/state/clawfedora-notion/references.json"

# Contrôle privé hors ligne.
python -m clawfedora.notion_references audit --page ID_WIKI \
  --capture-file "$HOME/.local/state/clawfedora-notion/references.json" \
  --output "$HOME/.local/state/clawfedora-notion/controle-liens.json"
```

Utiliser le jeton de lecture déjà prévu par l'inventaire. La capture lit les
objets du wiki et ne suit aucune destination. Les sorties sont des fichiers
privés neufs en mode `0600` sur un système de fichiers POSIX, hors Git.
L'audit affiche son statut et ne modifie aucune page.

## Couverture

- Liens Notion vers les pages, les bases et les blocs par identifiant,
  mentions, blocs de liens et ancres de blocs. Un lien qui inclut une page
  et une ancre est contrôlé par rapport à la page qui contient le bloc.
- Références présentes dans le texte enrichi, par exemple celles des
  exercices, corrigés ou guides d'installation, légendes, cellules et
  propriétés accessibles des pages.
- Liens GitHub, preuves GitHub Actions, URL de documentation reconnues
  et autres destinations externes. Une réponse HTTP ne certifie pas le
  contenu de la page ni le résultat d'un workflow.
- Pièces jointes visibles dans les blocs, propriétés, couvertures et
  icônes. L'expiration est comparée à l'heure de l'audit à partir des
  métadonnées Notion. Les octets ne sont pas téléchargés.

Les lignes de bases non inventoriées, widgets, copies synchronisées,
ancres textuelles, HTML brut et références hors wiki restent hors
couverture. Les URL externes avec paramètres, fragments ou identifiants
de connexion sont masquées, y compris dans les preuves. Les captures des
lots précédents contiennent des empreintes de structure et doivent être
renouvelées pour contrôler les destinations.

## Interpréter les résultats

| Signal | Interprétation |
| --- | --- |
| `present_in_inventory` | La destination apparaît dans le wiki observé. |
| `block_anchor_page_mismatch` | Le bloc apparaît sous une autre page que celle de l'ancre. |
| `outside_observed_inventory` | La destination est absente du périmètre inventorié. Elle peut exister dans une autre page ou nécessiter des droits différents. |
| `access_restricted` / `absence_unconfirmed` | Un code 401/403 indique un accès restreint. Un 404/410 de visibilité inconnue ne permet pas de confirmer l'absence. |
| `temporary_url_expired` | L'URL fournie au moment de la capture a expiré. Une nouvelle lecture peut émettre une autre URL pour la même pièce jointe. |
| `network_or_server_limited` | Échec réseau ou réponse telle que 429 ou 503. |
| `broken_confirmed_public` / `broken_confirmed_manual` | Un 404/410 a été observé sur une cible dont l'opérateur a établi la visibilité publique, ou l'absence a été confirmée par la revue. |
| `obsolete_confirmed` | L'opérateur a confirmé que la référence est obsolète. Un lien obsolète peut encore répondre. |

## Importer les observations opérateur

Ajouter `--observations /chemin/prive/observations.json` lors de l'audit.
Le JSON contient `schema` (valeur `1`), `capture_sha256` (recopié de la
capture) et `entries` (un objet par référence observée). Chaque objet porte
`reference_id`, `observed_at` en UTC et `result`.

- `http` ajoute `status_code` et `visibility` (`public` ou `unknown`).
  Utiliser `unknown` en cas de doute sur la visibilité, notamment pour
  les ressources GitHub privées.
- `network_error` indique une limitation réseau observée.
- `missing_confirmed` et `obsolete_confirmed` consignent une conclusion
  explicitement vérifiée par l'opérateur.

Les observations sont liées à la capture et datées entre la capture et
l'audit. Pour reproduire le résultat à une date fixe, fournir `--as-of`
au format UTC ISO 8601. Les empreintes vérifient la cohérence des fichiers.
Les observations restent des déclarations opérateur.

La recette utilise une API synthétique. Les essais sur Atlas et le poste
Fedora restent à réaliser.

[Rich text Notion](https://developers.notion.com/reference/rich-text) ·
[Fichiers Notion](https://developers.notion.com/reference/file-object) ·
[Codes d'accès GitHub](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api)
