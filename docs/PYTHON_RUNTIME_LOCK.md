# Reproductibilité des dépendances — Fedora 45

**Révision : 19 octobre 2026.** Le dépôt possède maintenant **deux niveaux distincts et complémentaires** : des versions exactes, et des empreintes cryptographiques vérifiées lors du téléchargement. Aucun verrou ne constitue à lui seul une preuve d'installation réussie sur le PC cible.

## Fichiers canoniques

| Composants | Manifeste | Installation |
| --- | --- | --- |
| Python de production et outils de build `setuptools`/`wheel` | [Versions communes](../config/python-runtime-constraints.txt) et [wheels SHA-256](../config/python-runtime-hashes.txt) | `pip install --require-hashes --only-binary=:all: -r config/python-runtime-hashes.txt` |
| Module voix optionnel (`faster-whisper` et ses dépendances) | [Complément SHA-256 voix](../config/python-speech-hashes.txt) | `pip install --require-hashes --only-binary=:all: -r config/python-speech-hashes.txt` |
| Application Python locale | `pyproject.toml` dans ce checkout | `pip install --no-deps --no-build-isolation -e .` après installation des outils de build épinglés |
| OpenClaw et plugin Parallel | [Contrat npm](../config/npm-runtime/package.json), [fermeture npm SHA-512](../config/npm-runtime/package-lock.json) | `npm ci --ignore-scripts` sur une arborescence privée ; aucune résolution flottante |
| Archives OpenClaw/Ollama | [SHA officiels directs](../config/install_artifact_integrity.json) | Vérification avant installation ; Parallel vérifié contre le `package-lock.json` |

Les wheels Python de production et de voix sont **tous pinés par version et par SHA-256** dans les fichiers de requirements ; les manifests contiennent les hashes de chaque wheel officiel publié pour les versions retenues, pas seulement la wheel de la CI. Les sources `sdist` sont exclues en production et voix ; aucune dépendance de build PEP 517 ne doit être téléchargée implicitement lors de l'installation de l'application locale.

La CI contrôle la validité des manifestes, la cohérence des versions et les installations propres Python 3.12/3.13, Fedora 45 et Node 24. Elle ne prouve pas la compatibilité avec toutes les versions de Python ou toutes les plateformes possibles.

## Procédure d'utilisation normale

**Aucune commande de verrouillage spéciale à lancer sur le poste** : les scripts `06_install.sh`, `00_bootstrap.sh`, `13_openwebui.sh` et `15_verified_installer.sh` utilisent les manifestes automatiquement.

Le vérificateur statique est accessible pour les contributions :

```bash
python scripts/validation/check_supply_chain_locks.py
python scripts/validation/check_python_lock.py
```

Le premier contrôle examine les contrats ; le second compare les versions réellement installées dans **l'environnement Python actif**. Sur Fedora, le programme de bootstrap les invoque dans le venv géré.

## Mettre à jour sans résoudre secrètement d'autres versions

1. Créer une branche dédiée, choisir explicitement les nouvelles versions souhaitées (OpenClaw, Parallel et dépendances Python) et consulter leurs changements de sécurité.
2. Pour npm, mettre à jour `config/npm-runtime/package.json`, puis, avec la version de Node/npm prise en charge, exécuter :
   ```bash
   npm install --package-lock-only --ignore-scripts --no-audit --no-fund --prefix config/npm-runtime
   npm ci --ignore-scripts --no-audit --no-fund --prefix config/npm-runtime
   ```
3. Pour Python, créer **un nouveau venv jetable**, installer les dépendances de production, de build et les extras voix désirés, vérifier `pip check`, puis réviser `config/python-runtime-constraints.txt`. Générer à partir des inventaires officiels PyPI :
   ```bash
   python scripts/validation/rebuild_python_locks.py            # aperçu
   python scripts/validation/rebuild_python_locks.py --apply    # met à jour les hashes
   ```
4. Relire le diff des versions et empreintes, contrôler `check_supply_chain_locks.py`, lancer tous les tests et inspecter l'installation native du plugin.
5. Fusionner **uniquement** après CI/CodeQL/Dependency Review verts. Ne jamais exécuter un gestionnaire de paquets avec `--no-verify` pour masquer un échec de hash.

## Frontières de la garantie

- Une empreinte prouve l'identité des octets téléchargés, **pas l'absence de vulnérabilité ni la signature de l'éditeur**. La provenance amont repose sur les registres officiels HTTPS au moment du verrouillage.
- Les dépendances **de développement** `.[dev]`, les paquets Fedora `dnf` et l'image Open WebUI (épinglée par digest lors du premier déploiement) suivent des politiques distinctes. Les verrous npm incluent les archives `inBundle` à travers l'empreinte SHA-512 de leur archive parente.
- `npm ci` et `pip --require-hashes` refusent une résolution différente plutôt que de choisir silencieusement une nouvelle version. Cela peut demander une PR si une archive est retirée du registre.
- Fedora 45, GPU B580, accès réseau privé effectif, voix, modèles et restaurations **restent à qualifier sur le PC réel** ; la CI n'est pas une réception matérielle.

[← Références](reference/README.md) · [Installation simple](INSTALLATION_SIMPLE_FEDORA45.md) · [Suivi des écarts](../STATUS.md)
