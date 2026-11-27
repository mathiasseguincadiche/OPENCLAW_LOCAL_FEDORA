# Recette synthétique du wiki Atlas — lot 10

La campagne clôt le périmètre logiciel synthétique du chantier C01. Elle
réutilise les cinq espaces de l'Atelier Atlas et présente six pages en
comptant l'accueil. Le scénario contient une base de suivi avec une source
et une vue, une procédure d'installation, des blocs synchronisés, une
archive et un exercice. Les réponses des API proviennent d'une fixture
locale.

| Lots | Contrôles exécutés |
| --- | --- |
| 1 à 3 | Compilation du studio, inventaire Markdown, pagination du wiki natif, propriétés de relation et de rollup, comparaison avant/après. |
| 4 à 6 | Répétition protégée, lien Notion présent, destination hors inventaire, accès GitHub restreint, URL expirée et copie divergente. |
| 7 et 8 | Plan de rationalisation, autorisation par tâche, refus d'un autre projet et collecte d'une preuve par le worker. |
| 9 | Édition de texte simulée sous approbation, refus du rejeu, préservation de l'installation, détection d'une archive altérée et retour à l'inventaire initial. |

## Reproduire

Depuis la racine du dépôt et avec les dépendances de test installées :

```bash
export NOTION_ATLAS_EVIDENCE="$(mktemp -d)/notion-atlas-c01.json"
GITHUB_SHA="$(git rev-parse HEAD)" pytest -q -s tests/test_notion_atlas_acceptance.py
```

La CI de la PR et de `main` expose le JSON dans l'artefact
`notion-atlas-c01-synthetic`. Le rapport est lié à la révision testée
par la CI. Le rapport contient les pages, le périmètre, les constats, les
liens, les propositions et les modifications simulées, le verdict de
non-régression, les preuves du worker et les empreintes du retour arrière.
Le verdict négatif de l'archive altérée est un résultat attendu du scénario.
Une campagne synthétique réussie porte le statut `CONFORME`.

Les permissions Notion réelles, les lignes de bases, les octets des médias,
le rendu et le poste Fedora restent `NON_VERIFIE`. L'exécution d'une
modification sur un wiki utilisateur est `NON_APPLICABLE` à cette
campagne. Pour la réception réelle, suivre la
[recette d'intégration](NOTION_GITHUB_ACCEPTANCE.md).
