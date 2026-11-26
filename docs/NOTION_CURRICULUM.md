# Notion avancé — parcours relationnel

[Studio Notion](NOTION_STUDIO.md) · [Exemple universel](editorial-demo/curriculum-spec.json)

Le studio accepte un parcours relationnel facultatif, à la place du suivi simple.
Il crée deux sources de données neuves sous le nouvel accueil :

| Base | Fonction |
| --- | --- |
| Modules du parcours | Objectifs, navigation vers la documentation, couverture et progression calculée |
| Activités du parcours | Actions ordonnées, objectifs, case de validation manuelle |

La relation unidirectionnelle Modules → Activités relie chaque module à ses
propres activités. Le rollup Progression calcule `percent_checked` sur
la case Validé. Toutes les cases sont initialement fausses : aucune preuve
ni compétence ne peut être déclarée acquise par le moteur.
Le chiffre représente exclusivement la part des activités cochées.

## Composition

L'opérateur choisit le nom, l'objectif, la page de référence et les activités
de chaque module. La carte contient un lien natif vers la sous-page de cours.
Une couverture privée PNG/JPEG peut être référencée par `cover_file` ; la
galerie utilise la couverture de page. Les modules sont triés selon l'ordre
du plan. Une vue filtrée ne montre que les activités non validées.

Utiliser la commande `plan` du [studio](NOTION_STUDIO.md), avec
`docs/editorial-demo/curriculum-spec.json` comme spécification.
Dans cet exemple sans image, ajouter les fichiers approuvés dans le
dossier média et leur nom aux modules si souhaité. L'aperçu local présente
les cartes, objectifs, activités et liens internes ; il ne simule pas
l'interactivité de Notion ni le rendu exact.

Le contrat accepte au plus cinq modules et douze activités, un seul
suivi (simple ou relationnel), huit médias et les autres limites du studio.
Les titres doivent être uniques. Les pages liées appartiennent exclusivement
à la création en cours. Aucune relation vers une base externe.

## Écritures et réception

Après création de la source Activités et de la source Modules, le moteur
relit le schéma de relation. Il ajoute le rollup uniquement à la source
Modules nouvellement créée, puis relit sa définition. Il crée les activités,
les cartes liées et contrôle la valeur initiale du rollup.
Il crée ensuite les deux vues et vérifie filtre, tri et couverture.
Aucune modification de pages ou de sources préexistantes.
L'écriture PATCH est limitée à l'endpoint des sources de données et
n'est pas enregistrée comme outil agent.

Les tests simulent l'API. Un résultat ambigu ou un rollup pas encore
calculé arrête la création : pas de retry d'écriture, ni rollback automatique.
Utiliser le reçu racine pour inspecter le résultat partiel. La réception
native sur une vraie page privée reste nécessaire.

## Références

- [Propriétés : relations, rollups](https://developers.notion.com/reference/property-object)
- [Configuration des vues](https://developers.notion.com/guides/data-apis/working-with-views)
- [Blocs natifs](https://developers.notion.com/reference/block)

Limites : blocs synchronisés, édition de wikis existants, relations
arbitraires, couvertures d'autres formats et contrôle visuel natif
restent hors de ce lot. Aucun changement d'agent ou modèle.
