# Studio Notion — création d'un wiki complet, lot 1

[Standard éditorial](EDITORIAL_PREMIUM_V2.md) · [Spécification de démonstration](editorial-demo/studio-spec.json)

Le module opérateur `python -m clawfedora.notion_studio` prépare la création
d'un **nouveau** wiki : accueil, une à six sous-pages, images locales PNG/JPEG
et couverture privée, une base de suivi optionnelle avec activités et vues
liste, galerie et tableau. Il n'édite pas les wikis existants.
Le contrat 2026-03-11 est isolé ; les autres moteurs Notion restent inchangés.

Le [parcours relationnel avancé](NOTION_CURRICULUM.md) est une alternative au suivi simple.

## Préparer

- Choisir une page de test dont le partage est **vérifié par l'opérateur**.
  Les nouvelles pages héritent de ses droits. « Téléversement privé » signifie
  Notion héberge les octets, sans publication GitHub ; ce n'est pas une
  garantie de confidentialité des permissions du parent.
- Créer un dossier privé de travail, copier la spécification JSON de
  démonstration, puis ajouter éventuellement `cover_file: "cover.png"`
  ou `images: [{"file":"visuel.png","caption":"Illustration"}]` à une page.
  Les images s'ajoutent après les blocs ; huit fichiers distincts maximum,
  4 Mo par fichier, 12 Mo au total, 64 à 4096 px, PNG/JPEG non animés.
  Utiliser un export raster contrôlé d'un SVG/Draw.io et garder les sources.
  Vérifier le contenu et les métadonnées sensibles avant envoi.
- Utiliser les jetons locaux existants NOTION_API_TOKEN (lecture) et
  NOTION_WRITE_TOKEN (écriture). La connexion doit autoriser l'insertion,
  la lecture et, pour les vues, la modification de contenu.

~~~bash
install -d -m 700 "$HOME/.local/state/clawfedora-studio/media"
cp docs/editorial-demo/studio-spec.json "$HOME/.local/state/clawfedora-studio/spec.json"
python -m clawfedora.notion_studio plan \
  --parent ID_PARENT_TEST \
  --spec "$HOME/.local/state/clawfedora-studio/spec.json" \
  --media "$HOME/.local/state/clawfedora-studio/media" \
  --output "$HOME/.local/state/clawfedora-studio/plan.json"
~~~

La commande lit le parent, vérifie les fichiers locaux et produit un
manifeste privé à 0600 avec contenu proposé, SHA-256 et taille des médias.
Aucun POST. Relire le plan et les fichiers eux-mêmes. Le fichier privé
`plan.json.preview.html` donne un aperçu local adaptatif des pages, médias
et suivi ; il embarque les images en base64 et doit rester hors Git.
Les liens et images externes ne sont pas chargés. Ce n'est pas le rendu natif.

~~~bash
python -m clawfedora.notion_studio apply \
  --plan "$HOME/.local/state/clawfedora-studio/plan.json" \
  --approve-parent ID_PARENT_TEST \
  --approve-manifest EMPREINTE_REELLE \
  --apply
~~~

Le plan expire après 24 h. Avant la première écriture, vérifier destination,
empreinte et octets. L'application crée un marqueur à usage unique.
Les fichiers sont transférés directement à Notion en multipart/form-data,
via le domaine API fixe, puis réutilisés par identifiant. Les pages,
propriétés, blocs, vues et état des uploads sont relus. Les activités
sont initialisées à « À réaliser » ; aucune progression inventée.

Une fois le premier accueil vérifié, son ID est enregistré dans
`plan.json.root.json`. En cas de panne partielle, consulter ce reçu (ou
le parent si la création de l'accueil n'a pas encore été confirmée).
Ne jamais relancer un plan tenté : pas de transaction atomique, rollback
automatique, suppression ni relance d'un POST ambigu. Une création
partielle reste possible, y compris un upload non encore attaché.
Les fichiers attachés deviennent persistants dans Notion : l'API ne permet
pas de révoquer un upload. Vérifier les autorisations avant approbation.

## Portée de qualification

La réception API ne valide pas les octets distants, le rendu, le recadrage,
les droits de partage ou le comportement des modèles. Les URL signées
de Notion ne sont ni téléchargées ni consignées dans les reçus.
Les tests automatisés simulent l'API. Une vraie page de test reste nécessaire.

Le suivi simple conserve ses galeries sans images de cartes. Le parcours
relationnel avancé ajoute des cartes illustrées, relations et rollups. Les liens complexes, les bases reliées,
les sous-pages à plusieurs niveaux, l'édition de wikis existants, les SVG
privés natifs et les médias volumineux restent des extensions distinctes.

## Contrat API

- [Envoi direct de petits fichiers](https://developers.notion.com/guides/data-apis/uploading-small-files)
- [Création de base](https://developers.notion.com/reference/create-database)
- [Bases et sources de données](https://developers.notion.com/guides/data-apis/working-with-databases)
- [Création et relecture des vues](https://developers.notion.com/guides/data-apis/working-with-views)

Version 2026-03-11, documentation consultée le 25 novembre 2026.

Le [profil de revue Notion](EDITORIAL_CYCLE.md) peut faire réviser une source
studio avant cette approbation. Il ne produit ni destination ni plan d'écriture.

Pour un wiki existant, le [module d'enrichissement contrôlé](NOTION_ENRICH.md)
ajoute une section après approbation et vérifie la conservation de l'inventaire direct.

## Navigation synchronisée facultative

Ajouter `"navigation": {"title": "Explorer le wiki"}` au JSON studio.
Le moteur crée un bloc synchronisé original dans l'accueil, avec les liens
vers l'accueil et toutes les sous-pages nouvellement créées. Une copie
référence cet original dans chaque sous-page. La maquette HTML montre
l'emplacement de cette navigation en fin de page. Aucun ID de page ou de
bloc externe n'est accepté dans la spécification de navigation.

Le plan et l'approbation existants couvrent cette option. Le moteur relit
les liens de l'original, les identifiants des blocs directs préexistants
dans les nouvelles pages et la référence de chaque copie. Un résultat
ambigu interrompt la création sans relance. Le reçu contient les IDs
de l'original et des copies. Les tests simulent l'API : le rendu natif
et la propagation réelle des modifications restent à qualifier. Aucun
wiki existant n'est modifié. Le contenu des blocs synchronisés n'est pas
édité par l'API (voir [référence Notion](https://developers.notion.com/reference/block#synced-block)).


[Inventaire natif récursif en lecture seule — lot 2](NOTION_NATIVE_INVENTORY.md).
