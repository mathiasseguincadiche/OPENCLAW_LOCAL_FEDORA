# Non-régression après édition Notion — lot 9

L'opérateur fixe l'état initial et le plan de texte qu'il a approuvé. Une
seconde lecture vérifie ensuite le résultat observable. La commande
prend en charge les plans existants de remplacement de texte simple,
pour un bloc ou [un lot de blocs](NOTION_MULTI_BLOCK.md).

1. Produire le plan d'écriture contrôlé et relever son empreinte.
2. Capturer le wiki avant d'appliquer le plan.
3. Sceller les attendus à partir de cette première capture et de
   l'empreinte approuvée du plan, puis conserver l'empreinte des attendus.
4. Appliquer le plan avec la commande d'écriture contrôlée habituelle.
5. Capturer le même wiki après l'opération, puis comparer les deux captures.

```bash
python -m clawfedora.notion_non_regression capture --page ID_WIKI \
  --output "$DOSSIER_PRIVE/avant.json"
python -m clawfedora.notion_non_regression prepare --page ID_WIKI \
  --edit-page ID_PAGE_EDITEE --before "$DOSSIER_PRIVE/avant.json" \
  --plan "$DOSSIER_PRIVE/edition.json" --approve-manifest SHA_DU_PLAN \
  --output "$DOSSIER_PRIVE/attendus.json"

# Après application via le workflow d'écriture contrôlé
python -m clawfedora.notion_non_regression capture --page ID_WIKI \
  --output "$DOSSIER_PRIVE/apres.json"
python -m clawfedora.notion_non_regression audit --page ID_WIKI \
  --before "$DOSSIER_PRIVE/avant.json" --after "$DOSSIER_PRIVE/apres.json" \
  --expectation "$DOSSIER_PRIVE/attendus.json" --expectation-sha256 SHA_DES_ATTENDUS \
  --output "$DOSSIER_PRIVE/rapport.json"
```

Les captures utilisent le jeton de lecture existant. La préparation et
l'audit sont hors ligne. Les sorties sont des fichiers privés neufs en
mode `0600` sur POSIX, hors Git. Le plan approuvé reste attaché au
[workflow d'écriture contrôlé](NOTION_CONTROLLED_WRITES.md), qui vérifie
ses propres préconditions avant toute édition.

Pour inclure des archives, sections d'installation ou rappels parmi les
éléments explicitement protégés, passer à `prepare` les
[annotations privées](NOTION_DUPLICATES.md) liées à l'inventaire embarqué
dans `references.inventory`. Les blocs synchronisés observés et leurs
descendants sont protégés automatiquement.

| Verdict | Signification |
| --- | --- |
| `CONFORME_OBSERVABLE` | Le texte exact et son environnement concordent. Aucun écart inattendu n'a été observé dans la couverture disponible. |
| `PARTIELLEMENT_CONFORME` | Une variation limitée aux métadonnées de transport ou aux limites de lecture demande une revue. |
| `NON_CONFORME` | Le texte attendu manque ou un écart imprévu a été observé. Le rapport est écrit et la commande renvoie le code 1. |
| `REFUSED` | L'intégrité, le périmètre, les entrées ou l'ordre des captures sont incompatibles. La commande renvoie le code 2. |

Le rapport vérifie l'identité et l'ordre des objets, les propriétés et vues
observables, les objets protégés et les références. Un renouvellement du
lien signé de la même pièce jointe peut changer sa date d'expiration sans
constituer un changement de référence. Les captures et le rapport
conservent des empreintes, des identifiants et des indicateurs.

Les capacités de l'inventaire bornent le résultat. La recette doit encore
vérifier Atlas et le poste Fedora. Les droits réels, les lignes de bases,
le rendu et le contenu des pièces jointes demandent des contrôles séparés.
La preuve établit l'état observé et demande une revue humaine.

[Rejouer le parcours complet sur Atlas](validation/NOTION_ATLAS_ACCEPTANCE.md).
