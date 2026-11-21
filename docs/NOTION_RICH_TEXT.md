# Notion — correction sûre d'un segment enrichi

[← Panneau Notion](NOTION_DASHBOARD.md) · [Lot multi-blocs simple](NOTION_MULTI_BLOCK.md) · [Recette intégrée](validation/NOTION_GITHUB_ACCEPTANCE.md)

## Pourquoi une voie d'édition distincte ?

Les PR #213, #215 et #216 prennent en charge un ou plusieurs blocs
**strictement textuels et non formatés**, avec approbation explicite.
Un bloc Notion réel peut contenir plusieurs segments : texte en **gras**,
*italique*, souligné, coloré, du code en ligne ou des **liens**. Remplacer
aveuglément tout le champ `rich_text` par un texte simple détruirait
ces détails.

Le nouvel éditeur `notion_rich` introduit une voie plus conservatrice :
**remplacer un seul segment de texte sans toucher aux autres segments**.
Il préserve explicitement les annotations existantes du segment modifié
et les autres segments, ainsi que l'icône et la couleur d'un encadré
Notion existant. <https://developers.notion.com/reference/update-a-block>
et <https://developers.notion.com/reference/rich-text> décrivent le
format Notion utilisé.

## Blocs concernés

- Paragraphe, titres H1/H2/H3, citation et éléments de liste simples.
- Encadré `callout` **existant**, avec icône et couleur conservées.
- Blocs de premier niveau, **sans enfants**, avec 1 à 16 segments
  textuels compatibles et moins de 9 000 caractères en tout.

Seuls les segments de type `text` sans lien sont modifiables. Le
programme conserve les autres segments, même si ceux-ci contiennent
des liens : leur URL, leur texte et leurs annotations sont inclus dans
la prévisualisation du changement. Les mentions `@page`, équations,
blocs avec enfants, objets de style inconnus ou incohérents sont
**refusés** plutôt que convertis ou simplifiés.

**Toujours non pris en charge :** création/suppression de pages,
tableaux, images, médias, base de données, éléments imbriqués,
réorganisation de blocs, remplacement d'une URL ou d'une mention,
édition du style lui-même, ainsi que publication autonome par les
agents. Aucune progression personnelle n'est créée ou validée.

## Utilisation dans l'atelier

1. Ouvrir `http://127.0.0.1:18890/notion.html` sur le Fedora
   hébergeant l'atelier et examiner une **page de test** explicitement
   sélectionnée (l'intégration doit y disposer d'un accès).
2. Dans **« Réviser un segment de texte enrichi »**, sélectionner
   le bloc et cliquer **« Examiner les segments et styles »**.
3. Identifier le segment exact à modifier. Les liens sont marqués
   non éditables. Ne remplacer **que** le texte de ce segment,
   en préservant son sens et le contexte des autres segments.
4. Produire la comparaison. Le moteur relit le bloc et les autres
   blocs de la page, calcule le plan et son empreinte **SHA-256**.
5. Recopier **l'identifiant exact de la page** et **l'empreinte exacte**
   du plan. Cocher l'approbation explicite, puis déclencher une
   seule application.
6. Ouvrir la page réelle Notion et vérifier le texte, les icônes,
   les couleurs, le formatage, les liens, l'affichage mobile, les
   sous-pages et la conservation de la **section installation des
   outils**.

Le navigateur n'accepte aucun jeton : le serveur emploie les
variables d'environnement `NOTION_API_TOKEN` (lecture) et
`NOTION_WRITE_TOKEN` (écriture) ; le plan privé est conservé
sous `runtime/state/notion-ui/`. Les secrets ne doivent être collés
dans aucun champ, prompt ou fichier versionné. L'approbation
est traitée côté serveur, sous contrôle d'origine et verrou
d'exécution.

## Préservation, conflits et vérification

Le plan contient une empreinte du bloc (texte, styles, dernière
modification, couleur et icône) et une empreinte de l'inventaire
des blocs directs de la page. Avant le PATCH, le moteur refuse
toute dérive détectée ; un reçu `ATTEMPTED` est créé avant l'appel
d'écriture. Il ne réessaie jamais silencieusement.

Après le PATCH, une nouvelle lecture API compare les segments
et les métadonnées visibles du bloc avec ce qui était attendu.
La réponse `RICH_SEGMENT_API_VERIFIED` indique une **concordance
API**, pas une validation graphique.

**Limites de concurrence :** Notion ne propose pas de comparaison
atomique d'une version avant PATCH. Ne pas éditer la page
simultanément avec plusieurs clients. Une interruption peut laisser
le texte modifié même si le navigateur signale un échec ; inspecter
la page Notion avant de produire un nouveau plan. Une normalisation
Notion (fusion ou découpe automatique des segments) peut également
faire échouer la vérification stricte après écriture.

## Réception avant usage sur les vraies pages

Tester sur une page isolée contenant un encadré coloré avec
trois segments : texte normal, texte en gras, puis lien. Modifier
le segment en gras ; contrôler le diff, l'empreinte, le texte final,
les autres segments, l'icône, la couleur et le rendu dans le
navigateur réel. Exécuter un essai avec une fausse empreinte et
un autre avec un segment changé entre le plan et l'application :
**aucune écriture** ne doit être lancée dans ces deux cas.

La CI exerce les chemins avec une API **simulée**. Le compte Notion
et le PC Fedora de l'utilisateur doivent être validés séparément.
