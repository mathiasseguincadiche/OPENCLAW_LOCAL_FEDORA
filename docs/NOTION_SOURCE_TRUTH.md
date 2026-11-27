# Sources de vérité et copies divergentes — lot 6

Le contrôle aide l'opérateur à localiser les références d'un projet et à
repérer les copies qui s'en écartent. Chaque sujet est propre au wiki,
par exemple une version, un état de projet, la séquence des exercices,
une décision d'architecture, un rappel de sécurité ou un schéma de
propriétés. L'opérateur désigne l'autorité pour chaque sujet.

## Lancer le contrôle hors ligne

```bash
python -m clawfedora.notion_source_truth --page ID_WIKI \
  --inventory "$HOME/.local/state/clawfedora-notion/inventaire.json" \
  --registry "$HOME/.local/state/clawfedora-notion/sources.json" \
  --output "$HOME/.local/state/clawfedora-notion/sources-audit.json"
```

L'[inventaire natif](NOTION_NATIVE_INVENTORY.md) peut être au schéma 1 ou 2.
Utiliser des fichiers privés hors Git sur un système de fichiers POSIX.
Le rapport neuf est écrit en mode `0600`. La commande ne contacte aucun
service et ne modifie aucun objet.

## Déclarer un sujet

Le registre JSON contient `schema` (valeur `1`), `root_page`,
`structure_sha256` recopiés de l'inventaire et le tableau `topics`.
Renseigner pour chaque sujet les champs suivants.

| Champ | Valeur |
| --- | --- |
| `key` | Identifiant du sujet propre au projet, composé de minuscules, chiffres, tirets ou tirets bas. |
| `canonical` | Tableau d'objets avec `category` et `id`. Une autorité unique permet la comparaison. |
| `copies` | Tableau des objets connus pour répéter la référence, dans le même format. |
| `comparison` | Type de preuve choisi selon la nature de cette référence. |

Le registre est lié à une capture. Après un changement de structure,
revoir les objets déclarés avant de reporter les rôles sur un nouvel
inventaire. Les références hors périmètre et les doubles attributions
à un même objet dans un sujet sont refusées.

| Comparaison | Preuve disponible |
| --- | --- |
| `normalized_text` | Empreinte textuelle d'un bloc. La casse, l'espacement, les liens et la mise en forme demandent une revue séparée quand ils sont significatifs. |
| `ordered_direct_text` | Séquence des empreintes des blocs textuels directs d'une page ou d'un bloc conteneur. Un même ensemble de textes dans un ordre différent déclenche `different_order`. |
| `property_type_profile` | Types et nombres de propriétés d'une source de données. Les noms, paramètres et lignes demandent une vérification séparée. |

`--annotations` accepte le fichier privé du [lot 4](NOTION_DUPLICATES.md).
Les objets annotés avec `truth_key` alimentent les candidats. Ils conservent
ce rôle même lorsqu'une divergence apparaît. Un sujet découvert sans
autorité déclarée apparaît comme `missing`. Les annotations peuvent
aussi signaler un contexte protégé, par exemple une archive ou un rappel de
sécurité. On peut lancer le contrôle avec les seules annotations.

`--reference-capture` accepte la [capture des liens du lot 5](NOTION_REFERENCES.md)
du même état de wiki. Parmi les copies et candidats du sujet, un bloc de
navigation `link_to_page` qui pointe vers l'autorité apparaît sous
`pointers`. Une mention intégrée dans un paragraphe reste un élément à
examiner avec le texte qui l'entoure.

## Lire les statuts

- `matching_observable_evidence` indique que les preuves sélectionnées coïncident.
- `divergent_observable_evidence` indique que ces preuves diffèrent.
- `different_order` indique un ordre observé différent.
- `insufficient_observable_evidence` indique une preuve absente ou incompatible.
- `no_unique_authority` indique une désignation absente ou plusieurs autorités en conflit.

Le rapport privé conserve les sujets, les emplacements, les contextes,
les empreintes et leurs limites. Un écart demande une revue du sens et
de l'usage avant toute modification. Deux copies peuvent volontairement
présenter des textes différents selon leur public. La recette utilise
des captures synthétiques. La vérification sur Atlas et Fedora reste à faire.
