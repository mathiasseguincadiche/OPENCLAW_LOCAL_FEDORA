# Installation : provenance et intégrité des composants

**Référence du socle neuf (18 octobre 2026)** : Fedora 45 Workstation / GNOME 51, OpenClaw **2026.10.4**, plugin Parallel **2026.10.4**, Ollama **0.40.6**, Open WebUI **v0.12.3-slim**. Ces valeurs correspondent au [manifeste des versions](../config/runtime_versions.yaml) et à la [politique WebUI](../config/webui_policy.yaml). **Elles ne prouvent pas une installation réussie sur le PC cible.**

Pour la procédure quotidienne, suivre [Installer Fedora et vérifier l'atelier](INSTALLATION_SIMPLE_FEDORA45.md) : le second disque doit être monté sur `/IA` et le runtime réside sous `/IA/Openclaw/`. **Les contrôles ci-dessous décrivent la sécurité de la chaîne d'installation, ils ne forment pas une deuxième installation à exécuter.**

## Composants et contrôles disponibles

| Élément | Origine et méthode | Garantie réellement apportée |
| --- | --- | --- |
| OpenClaw `2026.10.4` | Archive npm officielle | URL, version et SHA-512 figés dans [le manifeste d’intégrité](../config/install_artifact_integrity.json) |
| Plugin Parallel `2026.10.4` | Extension OpenClaw configurée | Version fixée dans `runtime_versions.yaml`, conformité du schéma testée avec OpenClaw natif |
| Ollama `0.40.6` | Archive Linux x86_64 officielle | SHA-256 vérifié **avant extraction** |
| Open WebUI `v0.12.3-slim` | Image `ghcr.io/open-webui/open-webui` | Résolution en digest SHA-256 au premier déploiement ; unité systemd enregistrée avec le digest |
| Python de production | `pip` avec fichier de contraintes | Versions directes et transitives communes contrôlées par [le verrou Python](PYTHON_RUNTIME_LOCK.md) |
| Runtime et données | Second disque monté sous `/IA` | Refus avant installation si `/IA` n'est pas le montage distinct attendu ; rejet des chemins non canoniques et liens symboliques dans les dossiers gérés ; services conditionnés au montage |

## Pourquoi l'installateur vérifie les archives

`scripts/linux/15_verified_installer.sh` n'exécute pas de script `curl | bash` téléchargé à la volée. Il vérifie l'archive autorisée et son empreinte officielle avant installation. OpenClaw est installé dans le préfixe utilisateur `~/.openclaw` avec `--ignore-scripts` ; le binaire Ollama est extrait sous `/usr/local`.

Après l'installation npm, `npm ls --global --all` rejette un arbre manquant ou incohérent. Cette vérification de cohérence **n'est pas** un audit complet des transitives npm ni une preuve de reconstruction cryptographique identique.

Le bootstrap Python ne fait pas de mise à niveau globale non bornée de `pip` / `setuptools` / `wheel`. Il applique `config/python-runtime-constraints.txt`, puis exécute `pip check` et le contrôleur de dérive. Le contrôle est également exercé dans la CI Fedora 45 et sur Python 3.12/3.13.

## Ce qui n'est pas totalement verrouillé

- Les **empreintes de chaque wheel Python** ne sont pas toutes figées ; les dépendances de construction PEP 517 peuvent varier selon la résolution et la plateforme.
- La **fermeture transitive npm** n'a pas de registre de hashes complet indépendant ; les paquets annexes de voix ont leur propre résolution.
- L'image Open WebUI est figée **lors de son déploiement**, pas par un digest préétabli et signé dans le dépôt.
- L'installateur et les services Fedora 45/GNOME 51 doivent encore être observés sur la machine réelle, notamment GPU/Vulkan, SELinux, WebUI et modèle.

Ces limites sont suivies dans [l'état actuel](../STATUS.md) et dans [l'issue de reproductibilité #126](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/126). Aucune documentation ne doit qualifier ces dépendances de « 100 % reproductibles » avant des preuves suffisantes.

## Installation neuve et migrations

Une installation Fedora neuve **n'importe pas silencieusement** les anciens états. Une éventuelle reprise se fait uniquement par `clawfedora-ops migrate-state --source CHEMIN --apply` après examen des sources et sauvegarde. Ne jamais lancer cette migration simplement pour suivre un guide d'installation neuve.

En cas d'échec d'empreinte, ne pas contourner les protections. Vérifier les publications officielles, corriger le manifeste par une PR spécifique puis repasser la CI. Les anciennes instructions d'installation sous OpenClaw 2026.10.3/Ollama 0.40.4 relèvent uniquement de [l'historique](archives/2026/README.md).

[← Documentation](README.md) · [Installation simple](INSTALLATION_SIMPLE_FEDORA45.md) · [Verrou Python](PYTHON_RUNTIME_LOCK.md)
