# Installation vérifiée : versions, artefacts et dépendances

**Révision : 19 octobre 2026.** Pour une installation neuve : Fedora 45 Workstation / GNOME 51, OpenClaw et plugin Parallel **2026.10.4**, Ollama **0.40.6** et Open WebUI **v0.12.3-slim**. [Versions canoniques](../config/runtime_versions.yaml) · [Politique WebUI](../config/webui_policy.yaml).

Pour l'utilisateur, seule la [procédure simple Fedora 45](INSTALLATION_SIMPLE_FEDORA45.md) est nécessaire. Les protections ci-dessous sont appliquées **automatiquement par les installateurs**, sans campagne de tests supplémentaire.

## Vérifications pendant l'installation

| Composant | Vérification effectuée |
| --- | --- |
| **OpenClaw** | Archive officielle npm en HTTPS, SHA-512 du [manifeste direct](../config/install_artifact_integrity.json) ; arbre npm complet imposé par `npm ci` avec SHA-512 du [package-lock](../config/npm-runtime/package-lock.json) |
| **Plugin Parallel** | Tarball officiel npm exact téléchargé en HTTPS, SHA-512 comparé au verrou avant installation locale par OpenClaw ; version 2026.10.4 revérifiée |
| **Ollama** | Archive Linux x86_64 officielle vérifiée par SHA-256 avant extraction |
| **Python de production** | [Wheels SHA-256](../config/python-runtime-hashes.txt), `pip --require-hashes --only-binary`, fermeture de versions communes et outils PEP 517 fixés ; installation du code local sans résolution PEP 517 implicite |
| **Voix** | [Fermeture voix](../config/python-speech-hashes.txt), incluant `faster-whisper` et ses transitives ; mêmes contrôles `--require-hashes` |
| **Open WebUI** | Image `ghcr.io` sélectionnée par version ; **digest relevé et verrouillé dans le service lors du premier déploiement**, pas pré-publié dans Git |
| **Stockage** | Volumes `/IA` distinct et monté, chemins canoniques sous `/IA/Openclaw`, rejet des liens sensibles, services conditionnés au montage |

## Garantie exacte

Le projet **ne lance pas de script distant `curl | bash`** pour installer OpenClaw/Ollama. Les commandes de paquetage utilisent un environnement privé, n'exécutent pas les scripts npm d'installation, contrôlent l'arbre installé et refusent toute erreur d'empreinte.

Dans le lock npm, les bibliothèques `inBundle` font partie du tarball parent authentifié par SHA-512 ; elles n'ont pas chacune une archive indépendante à télécharger. Les dépendances npm non incluses dans un bundle ont un `resolved` HTTPS et une empreinte. Les verrous Python contiennent les empreintes des wheels publiées pour ces versions, et aucun `sdist` n'est admis en installation de production/voix.

Fedora 45 utilise Python **3.15** pour son système ; le bootstrap crée un venv de l'atelier avec **Python 3.13** installé en parallèle pour garantir les wheels compatibles. Aucune modification de `/usr/bin/python3` ni compilation depuis `sdist` n'est nécessaire.

Les garanties ne sont pas absolues : le registre/éditeur amont n'est pas cryptographiquement attesté par une signature indépendante ; les paquets Fedora, outils de développement et modules WebUI ont des mécanismes distincts ; un paquet épinglé peut présenter une vulnérabilité. La CI valide une résolution **compatible avec ses environnements**, pas la qualité réelle de la B580 ou l'interface sur le PC utilisateur.

## Politique de mise à niveau

Les versions principales sont déclarées dans [`runtime_versions.yaml`](../config/runtime_versions.yaml). Toute évolution doit actualiser **ensemble** le manifeste des archives, le `package-lock.json`, les verrous Python concernés, les tests et les notes de version dans une PR. [Procédure de régénération des verrous](PYTHON_RUNTIME_LOCK.md).

Une installation neuve n'importe aucun ancien état. Toute migration depuis un ancien disque ou une ancienne version reste opt-in via `clawfedora-ops migrate-state --source CHEMIN --apply`, après sauvegarde.

**État de réception :** aucun déploiement réel Fedora 45/GNOME 51/B580 n'a encore été attesté. [État et limites](../STATUS.md) · [Tests avancés facultatifs](validation/README.md).
