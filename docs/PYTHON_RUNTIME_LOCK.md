# Dépendances : versions et empreintes vérifiées

Le dépôt conserve les versions exactes et les SHA-256 des distributions nécessaires
à l'installation du projet. La procédure refuse les archives non approuvées ;
aucune mise à jour automatique des dépendances n'est effectuée.

## Python 3.13 isolé sur Fedora 45

Fedora 45 conserve son Python système, sans rétrogradation. Le runtime IA,
séparé dans `/IA/Openclaw/runtime/venv/`, utilise le Python 3.13 distribué
par Fedora pour rester compatible avec les composants optionnels de voix.

| Ensemble | Verrou de versions | Empreintes |
| --- | --- | --- |
| Production (23 packages) | [Contraintes Python](../config/python-runtime-constraints.txt) | [SHA-256 runtime](../config/python-runtime-hashes.txt) |
| Voix facultative (21 packages) | [Contraintes voix](../config/python-speech-constraints.txt) | [SHA-256 voix](../config/python-speech-hashes.txt) |
| Outils de construction (setuptools/wheel) | [Contraintes de build](../config/python-build-constraints.txt) | [SHA-256 de build](../config/python-build-hashes.txt) |

Le bootstrap installe d'abord **setuptools et wheel depuis leurs wheels
hashées**, puis les paquets de production avec
`pip install --require-hashes --only-binary=:all:`. Cette combinaison refuse
les distributions sources qui auraient pu télécharger implicitement d'autres
outils de construction. Le projet local est ensuite installé avec
`pip install --no-build-isolation --no-deps -e .` : le backend de build
n'est ni téléchargé ni mis à niveau dans un environnement PEP 517 temporaire.

L'installation optionnelle de la voix suit le même principe, en ajoutant
sa fermeture indépendante de 21 paquets. Elle reste **désactivable**, sans
modifier les sept rôles ni le premier démarrage normal de Qwen.

Pour contrôler le dépôt, sans réseau ni installation :

```bash
python scripts/validation/check_dependency_artifact_locks.py
```

## npm : OpenClaw et Parallel

- [Manifeste npm](../config/npm-runtime/package.json) : OpenClaw et
  Parallel aux versions exactes de `config/runtime_versions.yaml`.
- [Lock npm v3](../config/npm-runtime/package-lock.json) : archives avec
  version, provenance et SHA-512 ; les sous-paquets `inBundle` sont
  inclus dans une archive parente vérifiée.
- L'installateur contrôle l'archive officielle OpenClaw puis effectue
  `npm ci --ignore-scripts --engine-strict` dans un répertoire temporaire
  avant de promouvoir la fermeture vérifiée. Parallel est chargé depuis
  le même arbre npm verrouillé ; aucune résolution npm indépendante.

## Ce que ces verrous ne prouvent pas

Les fichiers validés prouvent la cohérence des **versions, sources et
empreintes examinées**, mais non l'absence de vulnérabilités dans les paquets
tiers, la provenance humaine de leur publication ni le résultat matériel
sur la B580. Les RPM de Fedora, le Python et le gestionnaire de paquets
du système ne sont pas verrouillés octet par octet par Git. Les outils de
développement `.[dev]` restent hors de la fermeture Python de production.
L'installation et la restauration sur le PC réel restent à vérifier.

## Mise à niveau contrôlée

Une nouvelle version impose une PR qui réactualise les contraintes et leurs
SHA, le lock npm, les empreintes directes des archives, puis passe :
CI Python 3.12/3.13, conteneur Fedora 45 (runtime Python 3.13 et voix),
installation native OpenClaw/Parallel, ShellCheck, CodeQL et Dependency Review.

**Ne jamais contourner un refus de hash avec un `pip install` ou
`npm install` non verrouillé.** Diagnostiquer la version, le téléchargement
ou le manifeste avant de réessayer.

[← Références](reference/README.md) ·
[Installation](INSTALLATION_SIMPLE_FEDORA45.md) · [État actuel](../STATUS.md)
