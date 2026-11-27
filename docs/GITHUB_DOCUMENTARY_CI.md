# Workflows et preuves GitHub Actions au commit — C02, lot 4

L'audit rattache les workflows du dépôt, les exécutions GitHub Actions
et les liens de preuve publiés dans les documents à leur révision.

```bash
python -m clawfedora.github_document_ci \
  --github PROPRIETAIRE/DEPOT --commit SHA_COMPLET \
  --output "$DOSSIER_PRIVE/preuves-ci.json"
```

Utiliser le connecteur GitHub de lecture existant. La commande accepte
l'empreinte d'un [inventaire GitHub](GITHUB_DOCUMENTARY_INVENTORY.md)
du même dépôt avec `--inventory-sha256`. Le rapport est enregistré
dans un fichier neuf en mode `0600`, hors Git.

| Partie du rapport | Ce qu'elle vérifie |
| --- | --- |
| `workflow_definitions` | Fichiers YAML versionnés, identifiants de jobs, déclencheurs déclarés et identifiants des runs observés au chemin correspondant. |
| `runs` | Métadonnées officielles filtrées par SHA, événement, numéro de tentative, statut et conclusion. |
| `unmatched_run_ids` | Runs du SHA dont le chemin ne correspond à aucun fichier de workflow inventorié. |
| `document_references` | Références à un run dans le Markdown, avec emplacement, identifiant et SHA retourné par GitHub si l'accès le permet. |

Par défaut, l'audit lit `README.md` et `STATUS.md`. Pour sélectionner
d'autres fichiers, répéter `--document CHEMIN_MARKDOWN`. Un succès sur
un autre SHA est indiqué par `different_revision`. Un run inaccessible
reste `run_not_verified`, et les références à d'autres dépôts ne sont
pas interrogées. Pour un lien qui pointe vers un job ou un artefact,
la vérification porte sur le run parent.

Le rapport constate une absence de run observé sans en déduire un échec.
La lecture du YAML couvre sa structure principale. Elle n'évalue
ni le filtrage des déclencheurs, ni le contenu des étapes. L'audit
n'exécute aucun workflow et ne télécharge ni journaux ni artefacts.
Une conclusion GitHub Actions décrit l'exécution observée, tandis que
la qualification du poste Fedora ou d'un déploiement demande ses
propres preuves.

La commande délivre le rapport avec le code `0` et renvoie `2` si les
entrées, l'intégrité ou la pagination des runs ne permettent pas de
l'établir. Examiner les statuts du rapport pour décider de la suite.

[API GitHub Actions pour les workflow runs](https://docs.github.com/en/rest/actions/workflow-runs)

[Examiner les doublons et la frontière de diffusion](GITHUB_DOCUMENTARY_BOUNDARIES.md).
