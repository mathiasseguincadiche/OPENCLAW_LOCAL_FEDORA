# Notion — tableaux et illustrations existants

[← Panneau Notion](NOTION_DASHBOARD.md) · [Segments enrichis](NOTION_RICH_TEXT.md) · [Réception](validation/NOTION_GITHUB_ACCEPTANCE.md)

## Portée réelle

Le panneau local de l'atelier `http://127.0.0.1:18890/notion.html` possède
une section **« Tableaux et illustrations existants »**. Elle permet de
**consulter** les légendes d'images et les cellules d'un tableau natif
Notion existant, puis de préparer **une seule correction ciblée** avec
comparaison, empreinte et validation humaine.

- **Image** : modifier un segment de sa **légende**. Le bloc image reste
  au même endroit. Aucun fichier, image, URL externe ou ressource signée
  n'est remplacé, téléchargé ou transmis au navigateur. Une légende vide
  peut recevoir un premier segment.
- **Tableau simple** : modifier un segment d'une **cellule d'une ligne**
  existante. La largeur, les en-têtes, l'ordre des lignes, les autres
  cellules, leurs annotations et leurs liens sont conservés. Une cellule
  vide peut recevoir un premier segment.
- **Non pris en charge** : bases de données/vues Notion, ajout/suppression
  de lignes ou colonnes, fusion de cellules, redimensionnement, images
  nouvelles, téléversement de SVG/PNG, URL de ressource, édition de
  mentions et autres objets `rich_text` inconnus.

**Limites explicites :** tableaux de 1 à 12 colonnes et de 1 à 60 lignes,
une seule cellule ou légende par plan, au plus 1 900 caractères de nouveau
texte pour le segment. Les structures et contenus complexes sont refusés.
Le moteur actuel ne réalise pas de mise en page Notion complète.

## Déroulement dans le navigateur

1. Choisir une **page de test** partagée avec l'intégration Notion locale.
2. Cliquer **« Lister les blocs en lecture seule »**. Dans
   **« Tableaux et illustrations existants »**, choisir une image ou un
   tableau natif de la page.
3. Cliquer **« Examiner le contenu et les cellules »**. Pour le tableau,
   sélectionner la ligne, la colonne et le segment à modifier.
   Pour l'image, sélectionner le segment de légende.
4. Modifier le texte ; cliquer **« Prévisualiser sans écrire sur Notion »**.
   Relire le diff, vérifier les références GitHub, le sens des commandes,
   les en-têtes et les sections non ciblées.
5. Recopier l'**ID exact de page** et l'**empreinte SHA-256 exacte**,
   cocher l'accord explicite et appliquer **une seule fois**.
6. Ouvrir Notion dans son interface réelle et vérifier que la légende,
   les liens, les styles et les autres cellules restent corrects.
   Tester bureau et mobile ; comparer les schémas `.drawio` et `.svg`
   aux illustrations publiées.

Le jeton de lecture `NOTION_API_TOKEN` et le jeton d'écriture
`NOTION_WRITE_TOKEN` restent dans le processus local. Aucun secret
ne doit entrer dans la page HTML, dans un prompt IA ou dans le dépôt.
Les plans privés et reçus sont écrits sous
`runtime/state/notion-ui` avec permissions restrictives.

## Garanties et limites de concurrence

Avant de calculer le plan, le programme lit l'inventaire des blocs
de la page et les métadonnées du tableau, de ses lignes et du bloc
ciblé. Avant le PATCH, il revérifie ces éléments et refuse les
conflits détectés. Le plan expire après 24 h. Un fichier
`ATTEMPTED` est créé avant toute écriture pour interdire les
relances automatiques.

Pour une image stockée chez Notion, l'URL de téléchargement peut
changer d'une lecture à l'autre. L'éditeur exclut donc l'URL
signée et son expiration de l'empreinte d'identité du fichier ;
il conserve les autres vérifications, notamment le type de
ressource, le contenu et la date de modification du bloc.

L'API Notion ne garantit pas de **compare-and-swap atomique**.
Une écriture concurrente reste possible entre la dernière lecture
et le PATCH. En cas de réponse ambiguë ou d'échec de vérification,
ne pas relancer le plan : vérifier Notion et ses reçus, puis
préparer un nouveau plan après réconciliation.

La réponse `IMAGE_CAPTION_API_VERIFIED` ou `TABLE_CELL_API_VERIFIED`
signifie uniquement que le résultat attendu est relu via l'API.
Elle ne prouve pas la qualité graphique de la page, ni les
résultats des sept agents, ni l'installation sur Fedora.

## Ce qu'il reste à livrer

- Ajout contrôlé de **nouveaux** tableaux, images et schémas,
  avec gestion de l'hébergement et consentement spécifique.
- Prise en charge des lignes longues, des éléments imbriqués,
  des types de rich text non couverts et des opérations de
  réagencement.
- Recette graphique native réelle de Notion, en clair/sombre et
  sur mobile, puis tests du parcours complet sur Fedora.
