# Excellence éditoriale Premium V2

[Standard transversal](EXCELLENCE_EDITORIALE.md) · [GitHub](GITHUB_REPOSITORY_DESIGN_SYSTEM.md) · [Notion](NOTION_WIKI_DESIGN_SYSTEM.md)

## Ambition et limites

Standardiser la qualité et non l'apparence. Chaque projet doit avoir une identité visuelle
propre, un récit technique adapté à son besoin, une documentation navigable, des preuves
et une progression qui respecte l'autonomie personnelle. Le niveau minimal est
la proposition de studio OpsDesk V2 approuvée en direction ; elle ne constitue pas une
preuve d'exécution des modèles. Aucun nouveau modèle, agent ou service payant.

## Direction artistique : cinq variantes

Le moteur local `clawfedora_artifact` avec `format=identity` accepte un objet JSON encodé
dans content et retourne un SVG et sa source JSON normalisée. Deux rôles : architecte
et rédacteur ; sans réseau, sans SVG fourni par le modèle et sans exécution libre.

| Variante | Dimensions | Fonction |
| --- | --- | --- |
| cover | 1500 × 600 | Couverture sans texte critique, recadrage Notion à vérifier |
| hero | 1440 × 420 | Présentation GitHub |
| section | 1200 × 280 | Identité de rubrique |
| exercise | 1200 × 320 | En-tête de fiche |
| logo | 256 × 256 | Marque visuelle du projet |

Cinq motifs : network, pipeline, observability, platform, storage. Cinq palettes :
ocean, forest, ember, indigo, graphite, ou trois couleurs HEX personnalisées.
Le contrôle des contrastes porte sur des couleurs solides, pas sur le rendu natif.
Exemple de requête : filename=atlas.svg et content encodé depuis :

~~~json
{"project":"Atlas","tagline":"Concevoir, automatiser, exploiter","variant":"hero",
 "motif":"network","palette":"ocean","section":"Présentation"}
~~~

Conserver ensemble JSON et SVG. Ces illustrations ne sont pas des diagrammes
techniques : les schémas restent Draw.io + SVG. Ne jamais présenter une illustration
ou une maquette comme une capture réelle. Les motifs sont un catalogue initial,
pas une promesse de génération artistique libre.

[Exemples graphiques produits par le moteur](editorial-demo/premium/README.md).

## Rédaction, du besoin à l'action

- Ouvrir par le besoin métier, l'objectif et l'état réel ; un pitch spécifique.
- Expliquer la cause, le mécanisme, les conséquences et les limites.
- Montrer un exemple commenté distinct de l'exercice personnel.
- Lier décisions, alternatives et compromis ; ne pas réciter une stack.
- Expliquer où et pourquoi exécuter chaque commande, résultat attendu, premier
  écart, diagnostic, reprise. Préserver l'installation conditionnelle des outils.
- Relire transitions, rythme, terminologie, répétitions et phrases génériques.
  Un tableau sert une comparaison ; une illustration explique ou identifie.
- Conclure par ce que le lecteur peut maintenant comprendre ou faire.
  Ne pas déclarer de compétences sans pratique évaluée.

## Composition selon le support

| GitHub | Notion |
| --- | --- |
| Hero, pitch, navigation et état | Cover native, icône et titre |
| Présentation concise du service | Objectif et première action |
| Aperçu réel daté, picture clair/sombre | Espaces, mentions et colonnes courtes |
| Démarrage et architecture publique | Concepts, cours, préparation, exercices |
| Preuves, ADR, runbooks et limites | Suivi unique, indices, journal privé |

GitHub : Markdown natif, liens relatifs et alertes sobres ; pas de CSS libre.
Notion : composition native, titres utiles, images légendées, tables simples,
couvertures et liens enrichis. Les galeries, relations, vues et rollups existants
ne doivent jamais être dupliqués ou effacés pour une refonte graphique.

## Publication et qualification

Le [moteur de création Notion](NOTION_EDITORIAL_CREATION.md) accepte désormais une
couverture et des images externes GitHub épinglées sur commit, une icône et des
segments enrichis bornés. Ce sont des références publiques choisies explicitement ;
aucun transfert de fichier privé à GitHub. L'approbation du plan reste obligatoire.
Le [studio de wiki](NOTION_STUDIO.md) ajoute l'upload direct PNG/JPEG, les pages
filles et une base de suivi avec vues, dans un nouveau wiki et sous approbation.
Relations, rollups, autres formats et édition complète restent hors périmètre ;
ne pas assimiler capacité implémentée et qualification réelle.

La revue de contenu dispose de questions Premium V2 complémentaires à la grille
V1 : ouverture, explication, voix, composition, support, conservation. Aucune
note automatique. Rédaction par sections si nécessaire, audit indépendant,
corrections ciblées, nouvelle revue du diff puis réception native sur bureau clair,
sombre et mobile. En cas de contenu technique ou de rendu non vérifié, signaler
le manque de preuve. La CI ne certifie pas le comportement des modèles locaux.

## Références consultées

- [GitHub : mise en forme, images, liens relatifs, picture et alertes](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax)
- [Notion : blocs, notamment images externes](https://developers.notion.com/reference/block)
- [Notion : API de création de vues, version 2026-03-11](https://developers.notion.com/reference/create-view)
- [Notion : création d'un upload](https://developers.notion.com/reference/create-file)
- [Notion : envoi d'un upload](https://developers.notion.com/reference/upload-file)

Consultées le 25 novembre 2026. Le nouveau moteur de page conserve le contrat
API existant ; les nouvelles capacités de vues et d'upload ne sont pas annoncées
comme implémentées.
