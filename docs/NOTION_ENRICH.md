# Enrichissement contrôlé d'un wiki existant

[Studio Notion](NOTION_STUDIO.md) · [Boucle éditoriale](EDITORIAL_CYCLE.md)

Les outils de révision existants corrigent des blocs simples, des segments
enrichis ou des légendes avec approbation. Ce lot complète ces opérations
par l'ajout non destructif d'une nouvelle section native à la fin d'une
page existante, choisie par l'opérateur.

## Préparer

Créer une spécification JSON privée. Exemple :

~~~json
{
  "blocks": [
    {"type": "heading_2", "text": "Diagnostic"},
    {"type": "paragraph", "text": "Comparer l'état observé à l'état attendu."},
    {"type": "callout", "icon": "💡", "color": "blue_background",
     "text": "Vérifier avant de modifier la configuration."}
  ]
}
~~~

Les types de blocs sont ceux du compilateur éditorial : textes, listes,
code, tableaux, colonnes, toggles et images publiques versionnées, dans
leurs limites habituelles. Une section commence par un titre de niveau 2
et contient une explication. Aucun titre identique parmi les titres et
toggles directs existants. Maximum huit nouveaux blocs directs et cent
blocs directs au total. Une spécification de 6 000 octets maximum.

~~~bash
python -m clawfedora.notion_enrich plan \
  --page ID_PAGE --section section.json --output plan.json
~~~

Cette étape lit la page et ses blocs directs, scelle leur inventaire et
génère une maquette HTML locale de la section à ajouter. Elle ne modifie
pas Notion. Examiner la maquette, la pertinence et les doublons éventuels
dans les sous-pages, puis confirmer la destination et les droits de partage.

## Appliquer

~~~bash
python -m clawfedora.notion_enrich apply \
  --plan plan.json --approve-page ID_PAGE \
  --approve-manifest SHA256_DU_PLAN --apply
~~~

Le plan privé expire après 24 heures. Le jeton de lecture reste distinct
du jeton d'écriture. Le moteur compare les empreintes de la page et de
l'inventaire avant un seul PATCH d'ajout, enregistre un marqueur durable
avant toute écriture, puis relit les blocs directs et les nouveaux
sous-blocs. Le préfixe existant doit garder son ordre, ses identifiants
et ses données observables ; les URL temporaires des fichiers hébergés
et leurs expirations sont exclues de la comparaison. Le reçu scelle
l'inventaire et les identifiants des ajouts.

L'API ne fournit pas de transaction atomique ni de comparaison-et-échange.
Ne pas éditer la page en parallèle. Un résultat ambigu ou partiel exige
une inspection manuelle ; pas de retry ni suppression automatique.

## Limites

Le module ne modifie pas les blocs existants, les sous-pages, bases,
relations, rollups, couvertures ou progression. Il ne relit pas
récursivement les sous-arbres préexistants, ne vérifie pas les octets
distants des médias et ne certifie pas le rendu natif. Les blocs synchronisés
et le réagencement des pages ne sont pas créés par ce lot. Pour les pages
plus grandes, la pagination complète reste à ajouter. La création
de nouvelles sections ne remplace pas une revue du wiki entier.

Aucun outil d'écriture agent n'est ajouté. Aucun wiki réel n'a été modifié
par les tests : l'API est simulée. Qualification sur une page privée dédiée
nécessaire avant utilisation sur un espace de travail réel.
