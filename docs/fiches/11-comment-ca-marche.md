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
| **Passerelle cloud** (facultative) | Filtre, compte et relaie les appels vers OpenRouter ; seule à connaître la clé | Service de ton compte, port 18892 |

Tous les ports écoutent sur `127.0.0.1` : rien n'est accessible depuis un autre appareil. Hors cloud, aucune connexion ne sort de ton PC, hormis la recherche Web des rôles.

## Le trajet d'une question

1. Tu écris dans Open WebUI et tu choisis un rôle.
2. Open WebUI envoie la conversation à la passerelle.
3. La passerelle prend le verrou : si une génération est déjà en cours, elle répond « occupé ».
4. Elle garde les messages récents, y ajoute tes notes de suivi, et appelle OpenClaw pour ce rôle.
5. OpenClaw assemble ses consignes, celles du rôle et la description des outils, puis interroge Ollama.
6. Qwen répond. S'il demande un outil (une recherche Web, un fichier à produire), OpenClaw l'exécute et lui rend le résultat.
7. La réponse finale revient à Open WebUI, avec les liens des fichiers produits.

Un projet de l'atelier suit le même chemin à partir de l'étape 3, tâche après tâche.

## Le trajet d'une question au cloud

Si le cloud est activé et que tu as choisi le modèle « · cloud » (ou autorisé le projet), seule l'étape 5 change : OpenClaw n'interroge pas Ollama mais la **passerelle cloud** sur `127.0.0.1:18892`, avec un jeton local. La passerelle :

1. refuse tout si le cloud n'est pas activé (filtre et budget vérifiés ensemble) ;
2. scanne **tout le corps** de la demande : consignes, historique, contexte, appels d'outils et leurs résultats ;
3. si un secret est trouvé, répond 451 et n'envoie rien (le fil de chat passe en local, un projet se met en pause) ;
4. réserve le coût maximal dans le journal du budget, ou refuse (402) au plafond ;
5. appelle OpenRouter avec ta clé (lue dans un fichier privé, jamais donnée à OpenClaw) et les réglages imposés ;
6. note le coût réel, ou garde le pire cas si la réponse n'en donne pas.

Un tour avec un outil fait deux appels, donc deux passages par ces étapes. Il n'y a **aucun repli du local vers le cloud** : seul l'inverse existe dans le chat (avec bandeau), et l'atelier se met en pause.

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
| `config/core/model_routing.yaml` | Quel modèle sert chaque rôle (le même pour tous ; la route cloud est facultative) |
| `config/core/cloud_policy.yaml` | Le cloud : passerelle, modèle, budget, garde-fous ([détail](08-reglages.md)) |
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
- **La clé du cloud n'est lue que par la passerelle**, dans un fichier à droits 0600, et n'est jamais écrite dans la configuration d'OpenClaw, les journaux ni les sauvegardes. OpenClaw ne connaît qu'un jeton local, sans valeur auprès d'OpenRouter.
- **Le cloud est désactivé tant que le filtre et le budget ne fonctionnent pas ensemble** : l'activation est refusée si un contrôle échoue.

## Ce qui est testé, et ce qui ne l'est pas

| Vérifié automatiquement à chaque modification | Vérifiable seulement sur ton PC |
|---|---|
| Le code Python (tests, typage, style) | La carte graphique est bien utilisée |
| Les scripts shell (ShellCheck) | Le contexte tient dans la mémoire vidéo |
| La cohérence des fichiers de configuration | La vitesse des réponses |
| La configuration générée est acceptée par le vrai OpenClaw | La qualité des réponses de Qwen |
| Les consignes ne sont pas tronquées et le prompt tient dans le contexte | L'installation complète sur Fedora |
| Le filtre, le budget et la pause du cloud, avec le vrai OpenClaw et un faux fournisseur | Le cloud avec le vrai OpenRouter : coût réel, qualité de DeepSeek |

La colonne de droite est l'objet du [premier essai](02-premier-essai.md).
