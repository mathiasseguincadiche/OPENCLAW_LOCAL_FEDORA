# Atelier Fedora : migration locale Qwen + Ornith (22 novembre 2026)

## Décision

**Sept agents préservés, deux modèles Ollama obligatoires et zéro inférence payante.**

- `qwen3.5:9b-q4_K_M` : chef des opérations / mentor, recherche, architecte, sécurité, rédacteur pédagogique, auditeur qualité.
- `ornith-1.5:9b` : ingénieur DevOps ; Terraform, Ansible, Compose, Bash/Python, Kubernetes/K3s, CI/CD, diagnostic.
- **Aucun fallback implicite** : pas de fournisseur cloud dans la configuration produite. L'ancienne autorisation OpenRouter ne peut plus activer la route. Le worker refuse toute exécution `route=cloud`.
- Un seul modèle chargé simultanément en VRAM, avec files d'attente et sérialisation déjà prévues.
- Le routage principal est par agent, et non une nouvelle attribution automatique au hasard. Les demandes de contre-expertise sont des tâches distinctes soumises au worker.

## Motifs du choix

La cible matérielle est Intel Arc B580 12 Go, Fedora 45 et 48 Go de RAM partagés avec les laboratoires KVM. La variante Q4 de chaque modèle demande environ 6–7 Go de poids, **mais la VRAM totale dépend du cache KV et du contexte**. Le catalogue fixe 32 768 tokens. Les modèles sont chargés alternativement.

Ornith est spécialisé en programmation agentique et diagnostic terminal ; Qwen couvre la compréhension de consignes, la recherche, l'architecture, le français technique et la pédagogie. Les résultats publics de benchmark ne garantissent pas les performances sur la B580 ni la qualité d'un audit de sécurité.

## Mise à jour d'une installation existante

1. Sauvegarder l'état de l'atelier (projets et conversations) avant migration ; **ne pas purger le stockage existant**.
2. Arrêter la passerelle historique avec `./menu.sh --action cloud-disable --apply` avant la mise à jour. Cette opération ne résilie pas le compte OpenRouter et ne révoque pas automatiquement la clé fournisseur.
3. Révoquer manuellement la clé API OpenRouter sur le compte fournisseur. Conserver une copie de sécurité de l'ancien état avant toute suppression d'identifiants.
4. Prévisualiser l'installation, puis provisionner les deux modèles par les commandes de gestion existantes. Ne jamais considérer le téléchargement comme la preuve de fonctionnement GPU.
5. Adopter les nouveaux digests avec la commande `models-lock --apply` dans l'environnement géré, après avoir vérifié les identités et les quantifications.
6. Régénérer la configuration OpenClaw, vérifier qu'**Ollama est le seul fournisseur**, que les sept rôles existent, et que l'ingénieur DevOps utilise Ornith.
7. Faire la recette sur Fedora : contextes 16K/32K selon mémoire mesurée, appels d'outils, tests de refus cloud, survie des fils après redémarrage et contrôle de non-régression GitHub/Notion.

L'ancien code de passerelle et des références historiques figurent encore dans le dépôt : ils ne doivent **pas** être confondus avec une route opérationnelle. Leur purge documentaire et technique constitue un nettoyage distinct, à valider sans effacer les archives ni les états utilisateurs. Aucune facture ni aucun abonnement externe n'est annulé par cette modification du code.

## Périmètre de sécurité

Le fichier `config/core/tool_policy.yaml` conserve le refus de `exec`, `write`, `edit` et `apply_patch` pour les sept agents. Ce lot met en place le **routage local**, pas une exécution autonome libre. La réalisation agentique dans une copie de dépôt isolée exige une évolution distincte, avec commandes autorisées et validation humaine avant les opérations sensibles.

## Référence OpsDesk

Source : https://github.com/mathiasseguincadiche/OpsDesk

- Architecte Qwen : topologie `srv-admin`, `srv-app`, `srv-k3s`, réseau, flux, stockage et ADR.
- DevOps Ornith : Terraform/libvirt, Ansible/Rocky, Docker Compose, GitHub Actions, K3s, sauvegarde et diagnostic.
- Sécurité Qwen : SELinux, firewalld, SSH, secrets, dépendances et autorisations.
- Auditeur Qwen : comparer les critères aux sorties authentiques, jamais aux seuls récits du modèle.
- Mentor/rédacteur Qwen : cours et parcours des 13 exercices sans attribuer à l'apprenant des réalisations faites par l'IA.

**Statut : code de migration en revue.** Sans CI du dernier commit et sans réception sur la B580, aucune affirmation de conformité complète ou de performance réelle ne serait justifiée.
