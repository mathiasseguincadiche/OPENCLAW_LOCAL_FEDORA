# Création éditoriale Notion — périmètre contrôlé V2

[Standard](EXCELLENCE_EDITORIALE.md) · [Démo JSON](editorial-demo/notion-spec.json)

Le nouveau module `clawfedora.notion_editorial` compile une proposition JSON
typée en blocs natifs. Il est réservé à l'opérateur et n'est pas inscrit dans les
outils des agents. Il crée uniquement **une nouvelle page fille** sous un parent
explicitement choisi ; aucun remplacement de contenu existant.

## Préparation et utilisation

Choisir un parent de test privé déjà partagé avec l'intégration locale.
Vérifier ses droits ; les pages filles héritent des permissions du parent.
Conserver le plan hors Git dans un dossier privé (les fichiers créés sont en 0600).

~~~bash
install -d -m 700 "$HOME/.local/state/clawfedora-editorial"
python -m clawfedora.notion_editorial plan \
  --parent ID_PARENT_TEST \
  --spec docs/editorial-demo/notion-spec.json \
  --output "$HOME/.local/state/clawfedora-editorial/atlas-plan.json"
~~~

Le mode plan lit le parent et affiche le payload exact, l'empreinte du
manifeste et la destination ; aucune écriture distante. Après relecture,
recopier le vrai ID et l'empreinte exacte. Pour la première recette, ne pas
choisir le wiki OpsDesk ni une page publique.

~~~bash
python -m clawfedora.notion_editorial apply \
  --plan "$HOME/.local/state/clawfedora-editorial/atlas-plan.json" \
  --approve-parent ID_PARENT_TEST \
  --approve-manifest EMPREINTE_REELLE \
  --apply
~~~

Le jeton de lecture et celui d'écriture restent les mêmes variables privées
que les moteurs existants. Aucun secret dans les arguments ou le JSON.
Le plan expire après 24 h, le parent est relu, un marqueur ATTEMPTED
précède la création, puis le contenu est relu bloc par bloc, y compris
les enfants. Le reçu API_VERIFIED n'est pas une recette native graphique.
Pas de relance automatique ; en cas de réponse ambiguë, inspecter le parent
et les reçus. Notion ne fournit pas de transaction conditionnelle atomique.

## Blocs pris en charge

Paragraphes, titres, listes, citations, encadrés à palette limitée, code,
séparateur, sommaire, deux colonnes, toggle, tableaux simples.
30 blocs directs au plus, sous-groupes bornés. Le format refuse toute URL
de média non approuvée, base de données, opération destructive, champ arbitraire ou
imbrication non supportée. Les champs facultatifs cover et icon, les blocs image
avec url/caption et les blocs textuels avec spans sont pris en charge.
Les URL d'images sont strictement des ressources publiques raw.githubusercontent.com
épinglées sur un SHA de 40 caractères, sans query ni identifiants. Les liens de
segments visent une page Notion ou une référence GitHub immuable. Le contenu n'est
pas téléchargé par l'atelier. Le parent et le manifeste exact restent à approuver.

## Limites et réception

Les téléversements de fichiers locaux, les bases de données/vues, les mentions
complexes, les sous-pages multiples et la réorganisation d'un wiki existant ne
sont pas pris en charge par cette voie. La couverture et les images externes sont
à tester dans Notion ; la relecture API ne prouve pas que le fichier est visible. Le module vise l'API déjà utilisée
par l'atelier (2022-06-28). Les tests simulent les appels ; la réception
réelle sur une page de test et l'inspection visuelle bureau/mobile restent
requises. L'approbation du modèle ou du texte n'est pas une autorisation
de créer la page.

Référence : <https://developers.notion.com/reference/post-page> et
<https://developers.notion.com/reference/block>.
