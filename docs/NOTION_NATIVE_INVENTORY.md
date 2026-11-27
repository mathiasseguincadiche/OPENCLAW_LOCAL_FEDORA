# Inventaire et comparaison du wiki Notion — lots 2 et 3

[Outillage Premium des agents](NOTION_PREMIUM_AGENT_TOOLS.md) · [Studio Notion](NOTION_STUDIO.md)

Le nouvel inventaire opérateur lit un wiki réellement accessible par la connexion
Notion en version 2026-03-11. Il ne remplace pas l'instantané Markdown destiné
aux agents : il conserve une carte structurelle privée avec les identifiants,
parents, ordre des blocs, types et empreintes. Aucun texte brut, jeton ni URL
signée n'est conservé dans ce rapport. Aucun POST, PATCH, DELETE ou téléchargement
de média. Ne pas suivre les liens vers d'autres wikis.

## Utilisation

```bash
install -d -m 700 "$HOME/.local/state/clawfedora-notion"
# Plan : aucun accès réseau.
python -m clawfedora.notion_native_inventory --page ID_WIKI \
  --output "$HOME/.local/state/clawfedora-notion/inventory.json"
# Après choix explicite de la page et vérification du périmètre :
python -m clawfedora.notion_native_inventory --page ID_WIKI \
  --output "$HOME/.local/state/clawfedora-notion/inventory.json" --capture
```

Le jeton de lecture NOTION_API_TOKEN reste dans l'environnement local.
La destination doit être un dossier privé existant, hors Git, fichier neuf
0600. Aucun usage du jeton d'écriture. Le rapport n'est pas un plan d'écriture.
Le module n'est pas une capacité distante autonome du modèle.

## Contrôles

- Parcours récursif des pages filles et blocs imbriqués, pagination complète
  dans les bornes, ordre et parent vérifiés. Copies de blocs synchronisés et
  liens externes non suivis.
- Bases enfants, sources de données, types de propriétés (dont relations et
  rollups), vues du conteneur et empreintes des objets. Pas de requête vers
  les lignes ni les relations externes ; pas de lecture des widgets dashboard.
- Couvertures, icônes, blocs médias signalés ; pas de lecture des octets ni
  du rendu. Les URL hébergées temporaires sont exclues des empreintes.
- Budget 400 requêtes, 2000 objets, profondeur 16, 20 pages de pagination par
  liste ; cadence bornée. Refus si parent divergent, résultat incomplet, limite
  dépassée, objet répété ou API inaccessible. Pas de rapport favorable partiel.
- Le hash couvre les objets observables, pas une transaction atomique. Ne pas
  éditer simultanément. Les droits de partage réels, progression, lignes de
  bases, widgets, médias et rendu ne sont pas certifiés.

## Comparer deux captures hors ligne

Après avoir réalisé deux captures de la même page racine à des moments différents :

```bash
python -m clawfedora.notion_inventory_diff --page ID_WIKI \
  --before "$HOME/.local/state/clawfedora-notion/avant.json" \
  --after "$HOME/.local/state/clawfedora-notion/apres.json" \
  --output "$HOME/.local/state/clawfedora-notion/diff.json"
```

Renseigner les captures dans l'ordre chronologique. La commande utilise des
fichiers privés en environnement POSIX et écrit un fichier neuf en mode
`0600`, hors Git. Elle n'appelle ni Notion ni le worker. Le terminal affiche
uniquement le statut. Conserver le JSON en local car ses identifiants de pages
et de blocs restent privés.

| Champ | Interprétation |
| --- | --- |
| `added` / `absent` | Objets présents dans une seule capture du périmètre autorisé. Une absence peut provenir d'un déplacement hors périmètre ou d'un changement d'accès. |
| `modified.structure` | Parent ou position absolue modifiés. Une insertion peut décaler les positions sans réordonner les autres objets. |
| `reordered` | Ordre relatif modifié entre objets présents dans les deux captures sous le même parent. |
| `modified.fingerprints` | Variation du hash d'objet, du contenu observable, du texte normalisé ou du schéma de propriétés. |
| `modified.metadata_changed` | Indicateurs modifiés, dont types de propriétés, type de vue ou nombre de tris. |

Une page ou base enfant apparaît à la fois comme objet et comme bloc dans son
parent. Les deux entrées permettent de suivre ses métadonnées et sa place dans
la navigation. Une modification de parent ou de métadonnées d'édition peut
faire varier le hash d'objet `sha256`. Le schéma 2 ajoute
`observable_sha256`, qui en exclut le parent et les métadonnées d'édition,
ainsi que `properties_sha256` pour le schéma observable d'une source de données.
L'empreinte d'une vue varie si sa configuration observable change, même
quand le nombre de tris et la présence d'un filtre restent identiques.

Deux captures historiques du schéma 1 restent comparables avec leurs
empreintes d'origine et leurs indicateurs. Une paire de schémas 1 et 2 est
refusée. Pour les contrôles futurs, établir une nouvelle référence au schéma 2.
Le comparateur contrôle la structure, les totaux, les positions et les parents.
Le schéma 2 ajoute une empreinte de l'inventaire entier. Ces empreintes
recalculées contrôlent la cohérence des fichiers, sans authentifier leur
origine ni garantir les données que l'API ne montre pas.

Le rapport exige une revue humaine. Il conserve les limites de chaque capture.
Le lecteur doit vérifier les disparitions dans Notion avant d'en déduire une
suppression. Les empreintes ne contiennent pas de copie du texte, des lignes
de bases ni des fichiers, et ne permettent aucune restauration. Les tests
utilisent des réponses API synthétiques. La recette Atlas et la qualification
sur Fedora sont à réaliser.


Références officielles : [blocs enfants](https://developers.notion.com/reference/get-block-children),
[liste de vues](https://developers.notion.com/reference/list-views),
[version des API](https://developers.notion.com/reference/versioning).
