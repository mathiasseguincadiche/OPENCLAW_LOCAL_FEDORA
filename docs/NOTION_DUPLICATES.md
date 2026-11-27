# Détection des doublons dans le wiki Notion — lot 4

Le rapport aide l'opérateur à relire les redondances d'un inventaire privé.
Il réutilise les [contrôles de l'inventaire](NOTION_NATIVE_INVENTORY.md) et
accepte les schémas 1 et 2. La commande travaille sur des fichiers locaux.
Aucun appel à Notion, à un modèle ou au worker.

## Produire le rapport

```bash
python -m clawfedora.notion_duplicates --page ID_WIKI \
  --inventory "$HOME/.local/state/clawfedora-notion/inventaire.json" \
  --output "$HOME/.local/state/clawfedora-notion/doublons.json"
```

Les entrées doivent appartenir à l'opérateur et être privées, hors Git, dans
un dossier privé sur un système de fichiers POSIX. Le rapport est un fichier
neuf en mode `0600`, écrit une fois la validation terminée. Le terminal
affiche le statut. Les identifiants d'objets restent privés.

## Lire les signaux

| Famille | Signal | Interprétation |
| --- | --- | --- |
| Texte exact | Même type de bloc et même empreinte du texte normalisé. | Relire les blocs. La normalisation ignore les différences d'espacement et de casse. La mise en forme et les liens peuvent varier. |
| Bases de données | Même ensemble de profils de types de propriétés des sources, y compris leur multiplicité. | Examiner l'usage, les noms de propriétés et les lignes pour distinguer des bases légitimement similaires. |
| Sémantique | Équivalence annotée ou vocabulaire proche dans des extraits vérifiés. | Relire la signification et les différences, y compris les conditions et les négations. |
| Fonction et organisation | Même rôle fonctionnel ou organisationnel renseigné. | Vérifier si les deux objets servent le même lecteur ou le même parcours. |
| Navigation | Même destination interne renseignée pour plusieurs blocs. | Vérifier si les entrées simplifient l'accès depuis des points différents. |
| Sources de vérité | Plusieurs objets renseignés comme références du même sujet. | Vérifier où la donnée est maintenue et comparer les versions lors du lot dédié. |
| Schémas | Même empreinte d'un fichier de schéma fourni par l'opérateur. | Vérifier si la répétition apporte une vue utile pour le lecteur. |

Les deux premières familles sont examinées à partir de l'inventaire. Les
autres utilisent des annotations facultatives et apparaissent comme
`not_examined` lorsqu'aucun signal de la famille n'a été fourni.
Les blocs synchronisés et leurs descendants inventoriés sont protégés.
Une annotation peut protéger une archive, un rappel de sécurité, une
répétition pédagogique ou une section d'installation. La protection
d'une page se transmet aux objets qu'elle contient. Les correspondances
restent visibles sous `protected_context` pour éclairer la revue.

## Ajouter les éléments de contexte

Ajouter `--evidence /chemin/prive/annotations.json`. Le fichier privé contient
`schema` (valeur `1`), `root_page`, `structure_sha256` (recopiés de la
capture) et un tableau `entries`. Chaque entrée identifie un objet existant
avec `category` et `id`. Renseigner seulement les champs que l'on peut justifier.

| Champ d'une entrée | Valeur attendue |
| --- | --- |
| `context` | Liste parmi `archive`, `installation`, `security_reminder`, `synced_copy` et `teaching_repetition`. |
| `text` | Texte simple complet d'un bloc, dont l'empreinte normalisée correspond à la capture. La commande compare les ensembles de mots avec un minimum de 6 mots distincts et un seuil de similitude de 65 %. |
| `semantic_key`, `function_key`, `organization_key`, `truth_key` | Identifiant partagé quand la revue établit un même sujet ou rôle. Utiliser des lettres minuscules, chiffres, tirets ou tirets bas. |
| `navigation_target` | Objet `category` et `id` d'une page, d'une base ou d'un bloc du périmètre. L'opérateur établit la destination du bloc source. |
| `diagram_sha256` | SHA-256 des octets du fichier local revu pour un bloc image, fichier, PDF ou intégration. |

Les extraits sont comparés en mémoire. Le rapport conserve des signaux, des
identifiants et des empreintes d'intégrité. Il exclut les textes, les noms
des groupes annotés et les empreintes de fichiers jointes aux annotations.
Une annotation en dehors du périmètre, en double ou issue d'une autre capture
fait échouer la commande. La limite est de 300 objets annotés, dont 80
textes au maximum de 4 000 caractères chacun.

Les empreintes textuelles couvrent les blocs observables. La similitude
lexicale peut manquer des paraphrases et rapprocher des textes qui remplissent
des fonctions différentes. Les annotations d'équivalence, d'usage et de
destination reflètent la revue opérateur. Les faux positifs et les ruptures
de couverture doivent être examinés avant toute décision. Le rapport demande
une revue et ne déclenche aucune suppression. Les tests utilisent des
réponses API synthétiques, avec recette Atlas et validation Fedora à réaliser.
