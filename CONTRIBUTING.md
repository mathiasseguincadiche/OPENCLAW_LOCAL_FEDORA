# Contribuer

## Avant de proposer une modification

```bash
make install
make ci
```

`make ci` vérifie les fichiers de configuration, le style et le typage du code Python, les scripts shell, et lance les tests.

## Contrôles avec le vrai OpenClaw

Les tests de `make ci` utilisent des réponses de modèle simulées. Deux contrôles exécutent le vrai OpenClaw, sans modèle ni carte graphique :

```bash
make native-schema   # la configuration générée est acceptée par OpenClaw
make native-prompt   # les consignes ne sont pas tronquées et le prompt tient dans le contexte
```

Ils demandent `openclaw` dans le `PATH` et la variable `OPENCLAW_SCHEMA_PARALLEL_PATH` pointant vers le plugin Parallel de la même version. GitHub les lance sur chaque pull request. Ils sont nécessaires dès qu'on touche aux fichiers `agents/`, aux outils autorisés ou aux limites de `config/core/openclaw_policy.yaml`.

## Règles

- Le modèle reste local : pas de service cloud.
- Tout écoute sur `127.0.0.1`. Aucun script ne désactive SELinux ou le pare-feu.
- Les rôles ne reçoivent pas d'outil pour exécuter des commandes ou écrire directement des fichiers.
- Un script qui modifie le système affiche d'abord ce qu'il ferait ; il n'agit qu'avec `--apply`.
- La documentation change en même temps que le code : une fiche par sujet dans `docs/fiches/`.
- Les actions GitHub sont référencées par leur empreinte complète.
