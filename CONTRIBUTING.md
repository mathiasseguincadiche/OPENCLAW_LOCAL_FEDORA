# Contribuer

## Avant de proposer une modification

```bash
make install
make ci
```

`make ci` vérifie les fichiers de configuration, le style et le typage du code Python, les scripts shell, et lance les tests.

## Contrôles avec le vrai OpenClaw

Les tests de `make ci` utilisent des réponses de modèle simulées. Quatre contrôles exécutent le vrai OpenClaw, sans modèle ni carte graphique :

```bash
make native-schema   # la configuration générée est acceptée par OpenClaw
make native-prompt   # les consignes ne sont pas tronquées et le prompt tient dans le contexte
make native-tools    # les huit outils du plugin géré sont chargés et invocables
make native-cloud    # un tour cloud passe par la passerelle locale, qui voit les résultats d'outils
```

`make native-tools` vérifie le registre natif du plugin géré et ses helpers, sans modèle ni carte graphique. Il demande `openclaw` dans le `PATH`.

Les contrôles `native-schema`, `native-prompt` et `native-cloud` demandent `openclaw` dans le `PATH` et la variable `OPENCLAW_SCHEMA_PARALLEL_PATH` pointant vers le plugin Parallel de la même version. GitHub les lance sur chaque pull request. Ils sont nécessaires dès qu'on touche aux fichiers `agents/`, aux outils autorisés ou aux limites de `config/core/openclaw_policy.yaml`.

L'[assemblage des prompts et ses critères de validation](docs/PROMPTS.md) précise
le budget de 12000 caractères, les sorties JSON, les permissions et les documents
encore nécessaires pour terminer la confrontation aux références V2.3/V1.5.

## Règles

- Le modèle reste local par défaut. Le cloud est une option désactivée par défaut, joignable uniquement par la passerelle locale en boucle locale, qui seule détient la clé du fournisseur. Aucun repli du local vers le cloud.
- Tout écoute sur `127.0.0.1`. Aucun script ne désactive SELinux ou le pare-feu.
- Les rôles ne reçoivent pas d'outil pour exécuter des commandes ou écrire directement des fichiers.
- Un script qui modifie le système affiche d'abord ce qu'il ferait ; il n'agit qu'avec `--apply`.
- La documentation change en même temps que le code : une fiche par sujet dans `docs/fiches/`.
- Les actions GitHub sont référencées par leur empreinte complète.
