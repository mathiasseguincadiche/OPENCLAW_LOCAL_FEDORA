# Studio graphique avancé

[Galerie reproductible](editorial-demo/advanced/README.md) · [Standard Premium](EDITORIAL_PREMIUM_V2.md)

## Direction artistique

Le format `identity` accepte les six champs historiques et le champ
optionnel `composition`. Les sources existantes restent compatibles.

| Composition | Intention |
| --- | --- |
| split | Présentation classique, image et texte |
| editorial | Panneau visuel et hiérarchie éditoriale |
| orbit | Composition centrée sur le motif et anneaux |
| blueprint | Cadre technique et séparation des zones |

Sept motifs : network, pipeline, observability, platform, storage, security,
automation. Cinq palettes et trois couleurs personnalisables. Les compositions
sont déterministes ; les illustrations ne sont pas générées par un modèle
de diffusion. Les couvertures ne contiennent pas de texte critique.
Les logos et couvertures réutilisent certains motifs : le catalogue
n'est pas une identité de marque dessinée à la main.

## Schémas Draw.io

Toujours conserver la source éditable et le SVG. Pas de Mermaid.

| Layout | Usage |
| --- | --- |
| column | Chaîne verticale, compatibilité |
| flow | Parcours en grille |
| zones | Frontières et composants |
| timeline | Séquence horizontale |
| hub | Premier nœud explicitement central |

Les liens et composants restent ceux fournis. Les compositions timeline
et hub refusent les groupes : utiliser zones pour les frontières.
Limiter le nombre de nœuds et préférer plusieurs vues si nécessaire.
Une chaîne longue doit être contrôlée sur mobile ; ne pas supposer
qu'une réduction de taille préserve la lisibilité.

Le résultat `geometry_review` signale chevauchements des nœuds,
segments orthogonaux traversant un autre composant et liens non orthogonaux.
Ces signaux sont issus des coordonnées Draw.io ; ni test d'intersection
général, ni contrôle complet des labels, ni routage optimal, ni verdict
visuel. L'agent doit reprendre les flux signalés ou choisir une autre
composition, sans inventer de liens. Réception visuelle native obligatoire.

## Qualification

Tests de déterminisme, XML, compatibilité et géométrie. Galerie de référence
avec comparaison des octets en CI. La qualité typographique, le recadrage,
les thèmes et le rendu natif exigent une recette séparée.
