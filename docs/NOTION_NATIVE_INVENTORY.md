# Inventaire natif du wiki Notion — lot 2

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

Les tests utilisent une API simulée, incluant pagination, refus hors périmètre,
structure relationnelle et conservation privée. Qualification sur Atlas à faire.
Le prochain lot devra comparer deux états, relier les passages Markdown et
proposer une rationalisation non destructive, puis intégrer le plan au worker.

Références officielles : [blocs enfants](https://developers.notion.com/reference/get-block-children),
[liste de vues](https://developers.notion.com/reference/list-views),
[version des API](https://developers.notion.com/reference/versioning).
