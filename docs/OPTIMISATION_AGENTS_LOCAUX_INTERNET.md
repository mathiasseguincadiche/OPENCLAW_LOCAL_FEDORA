# Atelier local, connecté et productif — Qwen + Ornith

> **Implémentation en PR, pas encore réceptionnée sur Fedora/B580.**
> La documentation décrit les contraintes et les garde-fous, non une certification de performance.

## Périmètre : local pour l'inférence, connecté pour le travail

- Qwen 3.5 9B et Ornith 1.5 9B sont exécutés par Ollama sur `127.0.0.1:11434`.
- `OLLAMA_NO_CLOUD=1` empêche une utilisation accidentelle **des modèles distants et de la recherche propre à Ollama**. Cela **ne désactive pas** `web_search` et `web_fetch` d'OpenClaw.
- Les recherches Internet, les documentations officielles, les dépôts GitHub et les intégrations Notion restent accessibles **via leurs outils dédiés**, selon les habilitations existantes, avec sources non fiables et interdiction d'envoyer des secrets.
- Le mode Web privé demeure un choix explicite de l'opérateur et ne constitue pas le mode nominal. Le Web est activé par défaut dans `config/core/web_policy.yaml`.
- Un agent peut lire un site public mais ne peut jamais traiter son contenu comme une nouvelle instruction système ou comme une permission de publication.

## Orchestration et modèles

Le routage continue d'assigner Qwen aux six rôles généralistes et Ornith à l'ingénieur DevOps. Le worker garde le graphe de dépendances et la limite à une tâche concurrente. Parmi les tâches **déjà prêtes**, il privilégie celles dont le modèle correspond au modèle de la tâche précédente. Les tâches dépendantes n'ont jamais la priorité sur leurs prérequis.

Le raisonnement natif Ollama n'est plus désactivé par `params.think=false`. Pour les tâches du plan, le niveau d'effort explicite dépend du niveau **approuvé** par l'opérateur :

| Niveau | Effort demandé | Observation |
| --- | --- | --- |
| `simple` | `off` | priorité à la réponse directe |
| `complex` | `low` | raisonnement léger |
| `critical` | `medium` | raisonnement renforcé |

Pour un dialogue hors plan, les contrôles de réflexion d'OpenClaw restent disponibles. Le support natif du modèle doit être contrôlé via `/api/show` lors de la réception. Les limites de sortie et de mémoire doivent être surveillées avant d'augmenter l'effort.

## Sécurité : réalisation DevOps isolée et optionnelle

Le profil quotidien conserve le **refus** de `exec`, `process`, `edit`, `write` et `apply_patch` pour **les sept agents**. Il n'existe pas de shell LLM sur Fedora, ni d'accès au démon Docker ou aux clés SSH.

Le DevOps dispose désormais de `clawfedora_sandbox_validate`. Son fonctionnement :

1. L'agent propose **1 à 5 fichiers** (16 Ko au total) à partir d'un snapshot de tâche existant, déjà protégé par le worker.
2. L'opérateur doit **au préalable** installer et approuver manuellement une image OCI de validateurs **déjà présente localement**, identifiée par un digest SHA-256 et vérifiée.
3. L'outil copie uniquement les fichiers de code/configuration autorisés, puis ajoute les modifications proposées à cette copie temporaire.
4. Le laboratoire préexistant lance **un validateur prédéfini** via Podman rootless, sans réseau, sans privilèges, sans montage d'écriture et avec plafonds CPU/RAM/PID/temps.
5. Le résultat est une sortie de tests bornée et un reçu d'outil. **Ni le snapshot initial ni le projet central ne sont modifiés**.
6. Au maximum **trois validations par snapshot**. Après cela, l'agent doit s'arrêter et solliciter l'opérateur.

L'image OCI est un prérequis **local**. L'atelier ne télécharge ni n'installe automatiquement une image à la demande d'un LLM.

### Approuver l'image des validateurs

Choisir une image de validateurs que vous avez construite/auditée **avec les exécutables attendus** (Terraform, Ansible-lint, etc.) et déjà chargée dans Podman :

```bash
# D'abord lecture seule, puis accord explicite.
python -m clawfedora.devops_sandbox \
  --runtime /chemin/vers/le/runtime-gere \
  --image registry.example/validator@sha256:<DIGEST_REEL_64_HEX> 

python -m clawfedora.devops_sandbox \
  --runtime /chemin/vers/le/runtime-gere \
  --image registry.example/validator@sha256:<DIGEST_REEL_64_HEX> \
  --apply
```

**Remplacer les chemins et digest d'exemple.** L'accord sur une image n'autorise pas la fusion GitHub, un déploiement, un `terraform apply`, ou une modification de la VM. Un résultat Terraform `validate` ne prouve pas que le provider réel sera disponible en production.

### Boucle et résultats

La boucle fonctionne à partir des **retours réels des validateurs**, et pas d'une impression du modèle : proposition → `clawfedora_sandbox_validate` → analyse de la sortie → correction proposée → nouvelle validation (dans la limite de trois). Après un échec, aucune modification n'est appliquée au projet central ; les corrections restent des fichiers proposés à collecter et à revoir.

Le worker limite également à deux les exécutions d'une même tâche approuvée, et expose désormais l'état `blocked_local` si elles sont épuisées. Il ne passe jamais au cloud.

## Nouvelle boucle persistante (PR #243)

Le nouveau mécanisme `clawfedora_sandbox_iterate` conserve les révisions du code d'une tâche et produit des références immuables vers les fichiers ayant passé les validateurs. Le worker ne collecte que ces octets vérifiés, dans les chemins prévus et avec leurs reçus; la revue humaine est maintenue. La procédure, les limites et la préparation manuelle de l'image OCI sont détaillées dans [Boucle Ornith édition/tests/correction](BOUCLE_ORNITH_EDIT_TEST.md).

## Audit indépendant

L'auditeur reçoit les sources, le plan approuvé, les livrables et les preuves du projet. Son **snapshot d'audit retire** l'historique des discussions, les synthèses non vérifiées des producteurs et le résumé des résultats des tâches. Les véritables reçus d'outils, rapports de tests et pièces sont conservés. Un second avis Qwen n'est pas une garantie d'indépendance intellectuelle : le verdict reste soumis à des références et à des contrôles objectifs.

## VRAM et contexte

Les deux modèles sont toujours chargés alternativement (`OLLAMA_MAX_LOADED_MODELS=1`). Le contexte contractuel de 32 768 tokens est **conservé** jusqu'à la réception Fedora/B580. Ne pas afficher artificiellement des profils 16K/32K au niveau des agents : le `num_ctx` configuré dans le fournisseur OpenClaw fait autorité et doit rester cohérent avec le service Ollama.

Le cache KV `f16` demeure le choix de référence. Un passage à `q8_0` et Flash Attention nécessiterait des mesures sur **Qwen et Ornith** à contexte et prompts identiques, et une preuve via les journaux qu'ils sont réellement utilisés. Ce n'est pas une optimisation activée sans preuve.

## Recette sur la machine cible

- Vérifier `OLLAMA_NO_CLOUD=1` dans le service géré et que l'atelier peut toujours rechercher sur Internet et utiliser GitHub/Notion.
- Vérifier les identités SHA256, versions Ollama/OpenClaw et la résolution GPU B580.
- Mesurer 8K/16K/32K, temps de chargement, VRAM, qualité des appels d'outils et la compatibilité du raisonnement natif.
- Dans un projet de test : lancer les validations dans l'image OCI autorisée, contrôler les refus d'images non approuvées, liens symboliques, secrets et chemins hors workspace.
- Vérifier les circuits courts : une correction YAML ne doit pas déclencher sept spécialistes. Les jalons complexes restent soumis aux critères et audits.
- Vérifier le dossier de revue indépendant et l'arrêt des répétitions en état `blocked_local`.
- Exiger une revue humaine avant publication, changement d'infrastructure, secrets ou restauration.

## Références

- https://docs.ollama.com/faq
- https://docs.openclaw.ai/providers/ollama/advanced
- https://docs.openclaw.ai/gateway/sandboxing
- https://github.com/mathiasseguincadiche/OpsDesk
