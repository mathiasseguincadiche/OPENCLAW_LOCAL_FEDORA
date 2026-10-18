# Verrou Python de production — 18 octobre 2026

Les dépendances Python déclarées dans `pyproject.toml` ne sont pas toutes
épinglées : PyYAML, par exemple, accepte une plage de versions. La fermeture
Python **observée et installée** par la CI native Ubuntu/Python 3.12 au
commit `13843fcc` a été inscrite dans
`config/python-runtime-constraints.txt` (23 dépendances directes ou transitives).

Le bootstrap Fedora 45 installe désormais le projet avec
`pip install --constraint config/python-runtime-constraints.txt -e .` ;
le module voix conserve les mêmes contraintes pour la partie commune.
`scripts/validation/check_python_lock.py` compare les 23 versions exactes
aux distributions installées et refuse les écarts. Une CI de production vierge
exécute cette vérification en mode strict, sur **Python 3.12 et 3.13**.

## Vérification

```bash
python -m pip check
python scripts/validation/check_python_lock.py --strict
```

Le mode `--strict` suppose un environnement Python **dédié et vierge**,
sans dépendances de développement ni composants voix. Dans le venv Fedora
courant, exécuter sans `--strict` lorsque le module voix est installé ;
toute divergence dans les 23 pins reste bloquante.

## Limites documentées — à ne pas confondre avec une fermeture à 100 %

1. Le fichier est un verrou **de versions Python observées**, pas un
   `--require-hashes` : il ne fige pas les octets de chaque wheel,
   ni le miroir PyPI, ni l'environnement de build PEP 517.
2. `faster-whisper` et ses dépendances supplémentaires, les extras `dev`
   et la fermeture **npm/OpenClaw** ne sont pas contenus dans ce fichier.
   Ils doivent être traités séparément pour une reproductibilité totale.
3. La CI x86_64 sur Ubuntu/Fedora vérifie la résolution et les tests ;
   elle ne prouve pas le comportement du GPU Intel Arc B580 ni celui
   de GNOME 51 dans une session Fedora native.
4. Une montée de version doit régénérer les contraintes par une PR dédiée,
   lancer tous les tests, inspecter les différences et ne fusionner
   que si le rapport `runtime-lock` reste vert.

Aucun paquet système n'est mis à jour par la validation et aucune
donnée projet ou clé cloud n'est envoyée.
