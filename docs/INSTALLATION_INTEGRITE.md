# Chaîne d'installation vérifiée (OpenClaw 2026.10.2 / Ollama 0.35.1)

## Artefacts et références

Le manifeste `config/install_artifact_integrity.json` verrouille les **URL exactes, versions et empreintes** des archives officielles :

- **OpenClaw 2026.10.2 :** tarball npm depuis `registry.npmjs.org`, SHA-512 figurant dans la [publication officielle](https://github.com/openclaw/openclaw/releases/tag/v2026.10.2).
- **Ollama 0.35.1 :** `ollama-linux-amd64.tar.zst`, SHA-256 publié par GitHub pour le fichier de la [release v0.35.1](https://github.com/ollama/ollama/releases/tag/v0.35.1).

L'installateur `scripts/linux/15_verified_installer.sh` n'exécute **aucun script distant**. Il exige un utilisateur non-root, refuse une URL ou version non présente dans le manifeste, télécharge uniquement par HTTPS, recalcule SHA-256/SHA-512 **avant installation** et s'arrête si l'archive diverge. Ollama est installé depuis l'archive officielle Linux x86_64 vérifiée sous `/usr/local` ; OpenClaw est installé depuis son tarball npm vérifié sous `~/.openclaw` avec `--ignore-scripts`. Les commandes `--apply` modifient la machine : les aperçus sont non mutants.

Cette protection **ne garantit pas** que toutes les dépendances transitives résolues par npm possèdent un digest autonome inscrit dans le dépôt : un lockfile complet/provenance npm devrait renforcer encore cette chaîne. Aucun argument `latest` ni checksum récupéré en direct auprès du même téléchargement ne fait office de référence.

## Contrôles et procédure

Depuis une installation gérée Fedora 44 :
```bash
bash scripts/linux/15_verified_installer.sh openclaw
bash scripts/linux/15_verified_installer.sh ollama
./menu.sh --action validate
./menu.sh --action backup
./menu.sh --action upgrade     # aperçu
./menu.sh --action upgrade --apply
./menu.sh --action health
```

À la migration réelle, vérifier les chemins de l'exécutable Ollama et du service systemd, les groupes `render/video`, SELinux Enforcing, la version exacte et le fonctionnement de Qwen/Vulkan. La CI vérifie les pins, les refus de digest altéré et les aperçus ; **l'extraction des archives et le redémarrage systemd sur le PC restent à qualifier**.

En cas d'empreinte incorrecte : aucune tentative d'exécution ni installation ne doit suivre. Corriger uniquement après audit explicite d'une nouvelle publication officielle et revue des nouveaux hashes.
