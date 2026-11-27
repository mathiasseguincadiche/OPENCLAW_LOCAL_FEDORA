# Plans de rationalisation du wiki Notion — lot 7

Le plan donne à l'opérateur les constats à examiner avant toute décision.
Il rattache chaque constat à un objet inventorié et à l'empreinte du
rapport qui le justifie. C'est un document de revue privé, sans contenu
de remplacement ni instruction exécutable.

## Générer le plan

```bash
python -m clawfedora.notion_rationalization --page ID_WIKI \
  --inventory "$HOME/.local/state/clawfedora-notion/inventaire.json" \
  --output "$HOME/.local/state/clawfedora-notion/plan-rationalisation.json"
```

Un [inventaire natif](NOTION_NATIVE_INVENTORY.md) ou une
[capture des références](NOTION_REFERENCES.md) du même wiki suffit pour
commencer. Si seule la capture des références est utilisée, la passer
avec `--reference-capture` et omettre `--inventory`. La commande utilise
son inventaire embarqué. Les fichiers restent privés, sur un système
de fichiers POSIX et hors Git. La destination est un fichier neuf
écrit en mode `0600`.

| Entrée facultative | Effet sur le plan |
| --- | --- |
| `--before` | Ajoute un contexte de comparaison avec un inventaire antérieur. Une différence observée reste à examiner. |
| `--annotations` | Inclut les signaux enrichis et les protections du [lot 4](NOTION_DUPLICATES.md). |
| `--registry` | Inclut les conflits, divergences et preuves insuffisantes du [lot 6](NOTION_SOURCE_TRUTH.md). |
| `--reference-capture` | Inclut les constats du lot 5, à partir de la même structure d'inventaire. |
| `--observations` et `--as-of` | Ajoutent les observations externes liées à cette capture et fixent l'heure UTC de revue. Sans date, l'audit des liens utilise l'horodatage de la capture. |

Les rapports sont recalculés avec les outils existants. Leurs empreintes
figurent sous `evidence_reports`. Pour retrouver le même résultat que dans
un rapport déjà produit, utiliser les mêmes entrées et, pour les liens,
le même horodatage. Un rapport d'audit prérempli n'est pas une entrée
de cette commande. Un périmètre différent ou une capture incompatible
entraîne un refus avant la production du plan.

## Examiner le plan

Chaque constat contient un identifiant stable, une gravité de revue,
les emplacements concernés, la preuve observée, une proposition d'action
et son impact. Il indique aussi les objets et empreintes à préserver,
les préconditions, les approbations, la stratégie de retour arrière et
les vérifications de non-régression.

- Les conflits d'autorité et les liens confirmés cassés remontent en
  priorité.
- Les signaux de doublons protégés donnent lieu à une revue de leur
  usage. Les archives, rappels de sécurité, blocs synchronisés,
  répétitions pédagogiques et procédures d'installation sont à préserver.
- Les liens hors inventaire ou à accès restreint demandent une
  vérification. Une URL temporaire expirée oriente vers la relecture
  des métadonnées de la pièce jointe.
- Pour une copie divergente, la source déclarée et la copie restent
  identifiées dans les contenus à préserver.

Le retour arrière dépend d'une sauvegarde réelle du contenu et des
pièces jointes pertinentes. Les empreintes seules ne suffisent pas à
restaurer une page. Toute éventuelle écriture utilise un mécanisme
[contrôlé et approuvé](NOTION_CONTROLLED_WRITES.md) adapté à son périmètre.
La commande de plan ne réalise aucune mutation. Les tests sont
synthétiques. La recette sur Atlas et la qualification Fedora restent
à réaliser.

[Soumettre les preuves du plan au worker local](NOTION_WORKER_AUDIT.md).
