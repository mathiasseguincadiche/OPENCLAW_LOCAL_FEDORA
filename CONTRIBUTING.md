# Contribuer

## Avant de proposer une modification

```bash
make install
make ci
```

`make ci` vérifie les fichiers de configuration, le style et le typage du code Python, les scripts shell, et lance les tests.

## Contrôles documentaires

Toute PR qui change un comportement, une version ou un chemin doit mettre à jour **le document utilisateur correspondant**, le [sommaire](docs/README.md) si la navigation change, et le [statut](STATUS.md) si le niveau de preuve change. Vérifier les liens internes et que les commandes sont exécutables : `./menu.sh --action quick-check` vérifie une installation existante, il ne doit pas être lancé dans la CI ni être présenté comme obligatoire avant installation.

Les nouvelles pages doivent avoir un titre unique, un objectif clair, des commandes copiables et des limites explicitement nommées. Préférer un renvoi vers le guide de référence à la duplication d'une procédure. Les versions viennent de `config/runtime_versions.yaml`, `config/webui_policy.yaml` et `config/model_catalog.yaml`. Tout changement de version doit également réviser `config/npm-runtime/package-lock.json`, `config/python-runtime-hashes.txt` et `config/python-speech-hashes.txt` si concernés, puis exécuter `python scripts/validation/check_supply_chain_locks.py` ; **aucun numéro périmé** ne doit rester dans un guide opérationnel.

Les plans historiques sont indexés dans [Archives 2026](docs/archives/2026/README.md) ; ne pas supprimer un fichier référencé par un test ou une ancienne issue sans vérifier et corriger ses liens.

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

## Conduite

En contribuant, tu acceptes le [code de conduite](CODE_OF_CONDUCT.md).

## Règles

- Le modèle reste local par défaut. Le cloud est une option désactivée par défaut, joignable uniquement par la passerelle locale en boucle locale, qui seule détient la clé du fournisseur. Aucun repli du local vers le cloud.
- Tout écoute sur `127.0.0.1`. Aucun script ne désactive SELinux ou le pare-feu.
- Les rôles ne reçoivent pas d'outil pour exécuter des commandes ou écrire directement des fichiers.
- Un script qui modifie le système affiche d'abord ce qu'il ferait ; il n'agit qu'avec `--apply`.
- La documentation change en même temps que le code : une fiche par sujet dans `docs/fiches/`.
- Les actions GitHub sont référencées par leur empreinte complète.
