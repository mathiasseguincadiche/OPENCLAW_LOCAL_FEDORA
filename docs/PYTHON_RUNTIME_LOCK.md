# Dépendances : fermeture versionnée et empreintes d'artefacts

## Production Python — Fedora 45 (runtime Python 3.13 isolé)

Le projet contient deux fichiers complémentaires :
- [`python-runtime-constraints.txt`](../config/python-runtime-constraints.txt) : versions exactes des **23 dépendances de production**.
- [`python-runtime-hashes.txt`](../config/python-runtime-hashes.txt) : SHA-256 publics des archives sources et wheels **Linux x86_64** publiés par PyPI pour ces versions.

Fedora 45 garde **Python 3.15 pour le système**. L'atelier utilise un venv séparé basé sur **Python 3.13 fourni par Fedora**, afin de conserver la compatibilité avec la bibliothèque vocale CTranslate2, actuellement non distribuée pour cp315. Aucun Python système n'est rétrogradé.

Le bootstrap commence par `pip install --require-hashes -r config/python-runtime-hashes.txt`. Cette commande refuse un paquet sans hash validé, puis installe le projet avec `pip install --no-deps -e .`, sans résolution supplémentaire des dépendances de production.

**Contrôles en CI :** intégrité des manifests, installation Python 3.12/3.13 sur Ubuntu, installation réelle des distributions hashées sous Fedora 45 / Python 3.13, `pip check`, vérification des versions et tests. Le fichier des hashes contient des archives **sources** lorsque les wheels compatibles n'existent pas encore : dans ce cas, la compilation peut nécessiter des outils ou dépendances PEP 517 non couverts par ces hashes.

## npm — OpenClaw et plugin Parallel

- [Manifeste exact](../config/npm-runtime/package.json) : deux dépendances directes, `openclaw@2026.10.4` et `@openclaw/parallel-plugin@2026.10.4`.
- [Verrou npm v3](../config/npm-runtime/package-lock.json) : toutes les versions transitives, URLs du registre, hashes SHA-512 et paquets embarqués (leurs octets sont inclus dans une archive parente authentifiée).
- L'installateur vérifie d'abord l'archive OpenClaw et son SHA-512 direct, puis utilise **`npm ci --ignore-scripts --engine-strict`** dans un dossier de staging privé. Il vérifie la CLI et le plugin avant promotion dans `~/.openclaw/lib/node_modules`. Le plugin Parallel est lié **depuis ce même arbre verrouillé**, sans commande de mise à jour npm indépendante.

Une PR de changement de version doit mettre à jour le fichier d'intégrité directe, les versions, le `package-lock.json`, les SHA Python si nécessaire, lancer `npm ci`, `pip --require-hashes` et tous les contrôles. **Ne pas utiliser `npm install -g` pour contourner le verrou : npm global n'utilise pas le `package-lock.json` local.**

## Périmètre non démontré par les manifests

Les paquets Fedora (DNF/RPM) et les dépendances temporaires de compilation PEP 517 ne sont pas figés par SHA-256 ici. Les **21 dépendances optionnelles de voix** ont désormais leurs versions et empreintes SHA-256 dans [le verrou dédié](../config/python-speech-hashes.txt), avec une validation automatisée sur Fedora 45/Python 3.13. Les extras de développement `[dev]`, les dépendances de construction PEP 517 et les RPM restent hors du verrouillage cryptographique complet. La réception voix réelle (microphone, modèles, latence) est encore à effectuer sur le PC. Les tests GitHub ne prouvent ni le débit sur la B580, ni le comportement SELinux dans une session GNOME réelle.

Une empreinte SHA-256 vérifie l'intégrité **relativement à la valeur approuvée dans Git** ; elle ne prouve pas qu'un paquet tiers est exempt de vulnérabilités ni que son auteur est digne de confiance.

[← Références](reference/README.md) · [Installation](INSTALLATION_SIMPLE_FEDORA45.md) · [État des preuves](../STATUS.md)
