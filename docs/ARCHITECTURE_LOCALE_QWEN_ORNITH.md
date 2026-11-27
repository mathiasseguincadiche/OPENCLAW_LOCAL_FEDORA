# Architecture locale — Qwen 3.5 9B + Ornith 1.5 9B + Gemma 4 12B

> **Décision de migration, non preuve d'exploitation Fedora.** Ce document remplace la stratégie OpenRouter active. Les archives hybrides décrivent un état historique du projet, non un mode encore autorisé.

## Objectif

Un seul atelier graphique natif, sept agents OpenClaw spécialisés, une inférence locale Ollama **sans fournisseur API distant et sans facture de tokens**. Référence de cas réel : [OpsDesk](https://github.com/mathiasseguincadiche/OpsDesk), application FastAPI/React/PostgreSQL exploitée dans un laboratoire Fedora/KVM et trois VM Rocky.

La qualité visée est celle de **missions terminées avec des preuves**, pas une équivalence annoncée avec les grands modèles cloud.

## Affectation contractuelle

| Agent | Modèle principal | Mission | Outils et contrôles |
|---|---|---|---|
| `chef-operations` — mentor | **Qwen 3.5 9B** | Comprendre, expliquer, planifier, choisir les spécialistes strictement utiles | Lecture, recherche, trame, historique autorisé du projet ; worker décide de l'affectation |
| `expert-recherche` | **Gemma 4 12B** | Sources officielles datées, compatibilités, versions installées / annoncées | `web_search`, `web_fetch`, index local, citations |
| `architecte-solutions` | **Gemma 4 12B** | Topologies, réseau, choix techniques, ADR, schémas | `clawfedora_diagram` Draw.io/SVG, sources, critères de réception |
| `ingenieur-devops` | **Ornith 1.5 9B** | Terraform/libvirt, Ansible/Rocky, Docker, K3s, Bash/Python, CI, débogage | Artefacts de code, analyse de CI, lint et demandes de laboratoire |
| `ingenieur-securite` | **Gemma 4 12B** | Menaces, droits, secrets, SELinux, firewalld, chaîne de livraison | Contrôles statiques, Gitleaks, rapports Trivy, preuves, aucun verdict de sécurité fictif |
| `redacteur-pedagogique` | **Gemma 4 12B** | Guides, cours, runbooks, README, documentation GitHub et Notion | Sources approuvées, liens Markdown, exports modifiables et lisibilité |
| `auditeur-qualite` | **Gemma 4 12B** | Contrôler critères et résultats, sans corriger silencieusement | Lecture seule, SHA, reçus, CI, tests et provenance |

**Pourquoi trois modèles ?** Les évaluations Boréal, Silex et Quartz motivent la référence : Qwen pour le mentor et la vision, Gemma pour cinq rôles (7/7 sondes d'outils Silex), Ornith pour le DevOps. La supériorité code d'Ornith et les performances B580 restent à vérifier. Voir [consolidation](EXCELLENCE_NATIVE_QUALIFICATION.md).

**Pas de délégation native libre entre agents** : le worker orchestre. Le modèle principal de l'agent n'est pas remplacé silencieusement selon la longueur d'un prompt. Quand une étude architecturale exige du code, l'architecte transmet des exigences au DevOps ; quand un script est à corriger pour raisons de sécurité, la sécurité décrit le risque et le DevOps prépare la remédiation ; l'auditeur exige ensuite les sorties des validateurs.

## Exemples OpsDesk et preuves nécessaires

| Travail | Modèle de réalisation | Critère de réussite |
|---|---|---|
| Comprendre les frontières hôte / `srv-admin` / `srv-app` / `srv-k3s` | Gemma architecte / Qwen mentor | ADR avec flux, ports, secrets et incertitudes |
| Terraform + provider libvirt | Ornith DevOps | `fmt`, `validate`, plan enregistré et relu ; `apply` uniquement autorisé |
| Ansible / Rocky 10.2 | Ornith DevOps | lint, run sur VM de test, second passage `changed=0`, SELinux et firewalld vérifiés |
| Conteneurs / Compose | Ornith DevOps | sondes, ticket témoin, persistance, reboot sans confusion avec K3s |
| GH Actions / GHCR | Ornith DevOps | CI réelle, scan, diff, digest de l'image effectivement déployée |
| K3s | Ornith DevOps | copie de l'application, rollout/rollback sur la cible d'essai |
| Sauvegarde / reprise PostgreSQL | Ornith DevOps + Gemma auditeur | restauration isolée, ticket témoin, RPO/RTO observés |
| Wiki Notion et README | Gemma rédacteur + Gemma auditeur séparé | liens et chemins réels, fidélité aux preuves, rendu inspecté |

Les résultats de la CI d'OpsDesk ne sont pas des preuves d'un déploiement sur les VM. L'IA peut proposer des configurations ; les compétences personnelles se démontrent séparément.

## Matériel et chargement

- Hôte : Fedora 45 / GNOME 51, Ryzen 7 7700, 48 Gio RAM, Intel Arc B580 **12 Gio VRAM**.
- Ollama en **loopback** (`127.0.0.1:11434`), `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1` : Qwen, Ornith et Gemma sont chargés **alternativement**, jamais comme sept processus GPU indépendants.
- Catalogue : `qwen3.5:9b-q4_K_M` (texte + images) `ornith-1.5:9b` (texte/code) et `gemma4:12b-it-q4_K_M` (texte/outils). Les identités exactes doivent être adoptées et vérifiées par SHA-256 après téléchargement explicite.
- Contexte cible `32768` tokens : dépend de la VRAM réellement disponible et du cache KV. Aucune performance native B580 n'est attestée par une CI sur Ubuntu.
- Une exécution locale évite la facturation *d'inférence*, mais pas l'électricité ou les ressources consommées par tes VM.

## Sécurité et retrait d'OpenRouter

Le catalogue ne déclare **que** Ollama ; le routage local est obligatoire ; le cloud est retiré dans le contrat. `cloud_status` doit toujours refuser l'activation et `build_openclaw_patch(..., cloud_enabled=True)` refuser de générer un fournisseur. Les anciennes commandes cloud ne doivent jamais réactiver une passerelle ou enregistrer une nouvelle clé.

Pour une ancienne installation gérée, après sauvegarde vérifiée :

```bash
./menu.sh --action local-retire-cloud
./menu.sh --action local-retire-cloud --apply
./menu.sh --action models
./menu.sh --action models --apply
./menu.sh --action configure-openclaw --apply
./menu.sh --action health
```

Le retrait arrête l'ancien service de passerelle et efface **uniquement** la clé locale, le jeton de passerelle et l'activation après les vérifications de chemin. Les journaux de facturation historiques sont conservés. Cela n'annule ni abonnement Anthropic ni recharge automatique éventuellement activée chez un fournisseur : ces opérations restent à faire sur leurs sites respectifs.

**Important :** les agents restent aujourd'hui en lecture/proposition de fichiers, avec outils spécialisés. `exec`, `edit`, `write`, `apply_patch` et l'administration privilégiée sont interdits en profil quotidien. L'ajout d'une boucle autonome *modifier → tester → corriger* nécessite un chantier distinct avec workspace jetable, commandes autorisées, validations avant publication, preuve de rollback et isolation du PC. Ne pas présenter cette migration de moteurs comme une telle fonctionnalité déjà opérationnelle.

## Réception et refus de faux succès

1. Contrats, Ruff, Mypy, ShellCheck, tests Python et schéma OpenClaw natif sur le commit de la PR.
2. Trois modèles réellement téléchargés, identités Q4 et digests conformes au verrou.
3. Chaque rôle reçoit exclusivement le modèle contractuel ; aucun provider `cloudgw` n'est exposé ; `route=cloud` et CLI héritée refusées.
4. Test d'inférence sur chaque modèle, saturation 8K/16K/32K, cache et charge GPU de la B580 mesurés sur Fedora.
5. Tests fonctionnels InfraOps réels et reçus : les fichiers valides ne prouvent ni infrastructure déployée ni travail personnel.
6. Historique des discussions, projets GitHub/Notion et permissions conservés.

**Statut : migration de code en PR ; réception Fedora, performances, et workflows agentiques complets non vérifiés.**

## Références de modèles

- [Qwen 3.5 9B sur Ollama](https://ollama.com/library/qwen3.5)
- [Ornith 1.5 9B sur Ollama](https://ollama.com/library/ornith-1.5)
- [Ornith 1.5 9B — fiche et benchmarks de l'éditeur](https://huggingface.co/ornith-ai/Ornith-1.5-9B)
