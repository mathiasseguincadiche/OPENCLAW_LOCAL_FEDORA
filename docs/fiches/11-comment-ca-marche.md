# Comment ça marche

[← Guide](../GUIDE.md)

## Les pièces

![Deux interfaces, un même moteur](../diagrams/atelier-architecture.svg)

| Pièce | Rôle | Où elle tourne |
|---|---|---|
| **Ollama** | Charge Qwen sur la carte graphique et produit le texte | Service système, port 11434 |
| **OpenClaw** | Applique à chaque demande les consignes et les outils du rôle choisi | Service de ton compte (Gateway), port 18789 |
| **Passerelle de chat** | Relie Open WebUI à OpenClaw | Service de ton compte, port 18891 |
| **Open WebUI** | L'interface de discussion | Conteneur Podman, port 3000 |
| **Atelier Projets** | L'interface des projets et le moteur qui ordonne les tâches | Service de ton compte, port 18890 |
| **Outils métier** | Fabriquent les fichiers, schémas et contrôles pour les rôles | Plugin `clawfedora-toolkit` chargé par OpenClaw |

Tous les ports écoutent sur `127.0.0.1` : rien n'est accessible depuis un autre appareil.

## Le trajet d'une question

1. Tu écris dans Open WebUI et tu choisis un rôle.
2. Open WebUI envoie la conversation à la passerelle.
3. La passerelle prend le verrou : si une génération est déjà en cours, elle répond « occupé ».
4. Elle garde les messages récents, y ajoute tes notes de suivi, et appelle OpenClaw pour ce rôle.
5. OpenClaw assemble ses consignes, celles du rôle et la description des outils, puis interroge Ollama.
6. Qwen répond. S'il demande un outil (une recherche Web, un fichier à produire), OpenClaw l'exécute et lui rend le résultat.
7. La réponse finale revient à Open WebUI, avec les liens des fichiers produits.

Un projet de l'atelier suit le même chemin à partir de l'étape 3, tâche après tâche.

## Pourquoi un verrou

La carte n'a que 12 Go. Deux générations en même temps se partageraient la mémoire et la vitesse. Le chat et l'atelier partagent donc un seul verrou (`/srv/openclaw-local/state/worker.lock`) : une génération à la fois, pour tout le monde. Le mode jeu et les opérations d'entretien prennent le même verrou.

## Le dépôt

```text
menu.sh              point d'entrée : toutes les commandes passent par lui
agents/              consignes des sept rôles
config/              réglages : modèle, versions, limites, outils autorisés
plugins/             outils métier chargés par OpenClaw
scripts/linux/       étapes d'installation et d'entretien, numérotées dans l'ordre
scripts/validation/  contrôles qui exécutent le vrai OpenClaw
src/clawfedora/      le code Python : atelier, passerelle, génération de la configuration
tests/               tests automatiques
docs/                ce guide et ses fiches
```

## Les fichiers de configuration

| Fichier | Ce qu'il fixe |
|---|---|
| `config/model_catalog.yaml` | Le modèle utilisé |
| `config/runtime_versions.yaml` | Les versions exactes d'OpenClaw et d'Ollama |
| `config/core/openclaw_policy.yaml` | Contexte, longueur des réponses, taille des consignes |
| `config/webui_policy.yaml` | Open WebUI : image, ports, mémoire, historique |
| `config/core/agents.yaml` | La liste des sept rôles |
| `config/core/model_routing.yaml` | Quel modèle sert chaque rôle (le même pour tous) |
| `config/core/tool_policy.yaml` | Les outils autorisés et interdits par rôle |
| `config/core/web_policy.yaml` | La recherche Web |
| `config/core/knowledge_policy.yaml` | La recherche dans les documents d'un projet |
| `config/core/orchestration_policy.yaml` | Les états d'un projet et leurs transitions |
| `config/core/intake_policy.yaml`, `document_ingestion_policy.yaml`, `artifact_exchange_policy.yaml` | L'import des documents et l'échange de fichiers entre tâches |
| `config/hardware.yaml`, `config/platform.yaml` | La machine et le système attendus |
| `config/lifecycle_policy.yaml` | Installation, sauvegarde, désinstallation |

Tu modifies ces fichiers, puis `./menu.sh --action validate` vérifie qu'ils restent cohérents entre eux, et `./menu.sh --action install --apply` les applique. La configuration d'OpenClaw n'est jamais éditée à la main : elle est générée à partir de ces fichiers par `src/clawfedora/openclaw_config.py`.

## Ce qui protège ton PC

- **Rien n'est exposé au réseau.** Tous les services écoutent sur `127.0.0.1` et aucun port du pare-feu n'est ouvert.
- **SELinux reste actif.** Aucun script ne le désactive.
- **Le modèle ne peut rien exécuter.** Les outils de commande, d'écriture et de navigation sont interdits dans la configuration d'OpenClaw.
- **Le modèle ne peut pas se mettre à jour.** L'outil d'OpenClaw qui le permettrait est interdit, et les versions sont vérifiées à chaque message.
- **Les documents et pages Web sont traités comme des données.** Un texte qui dirait « ignore tes consignes » n'a aucune autorité.
- **Open WebUI tourne dans un conteneur sans privilèges**, limité à 3 Go de mémoire et 2 cœurs, sans accès à ton dossier personnel.

## Ce qui est testé, et ce qui ne l'est pas

| Vérifié automatiquement à chaque modification | Vérifiable seulement sur ton PC |
|---|---|
| Le code Python (tests, typage, style) | La carte graphique est bien utilisée |
| Les scripts shell (ShellCheck) | Le contexte tient dans la mémoire vidéo |
| La cohérence des fichiers de configuration | La vitesse des réponses |
| La configuration générée est acceptée par le vrai OpenClaw | La qualité des réponses de Qwen |
| Les consignes ne sont pas tronquées et le prompt tient dans le contexte | L'installation complète sur Fedora |

La colonne de droite est l'objet du [premier essai](02-premier-essai.md).
