# Références techniques

Cette section s’adresse à une personne souhaitant vérifier **pourquoi** l’atelier est construit ainsi et **comment** ses protections fonctionnent. Pour l’installation quotidienne, préférer [le guide court](../INSTALLATION_SIMPLE_FEDORA45.md).

| Sujet | Document et source de vérité |
| --- | --- |
| Architecture des deux moteurs | [Architecture hybride](../ARCHITECTURE_HYBRIDE.md) · [Politique de routage](../../config/core/model_routing.yaml) |
| OpenClaw, Ollama, WebUI | [Intégrité de l’installation](../INSTALLATION_INTEGRITE.md) · [Versions déclarées](../../config/runtime_versions.yaml) |
| Dépendances Python | [Verrou des versions de production](../PYTHON_RUNTIME_LOCK.md) |
| Passerelle DeepSeek et budget | [Passerelle cloud](../PASSERELLE_CLOUD.md) · [Contrat cloud](../../config/core/cloud_policy.yaml) |
| Recherche Web privée | [Mode Web privé](../WEB_ACCESS_PRIVATE_MODE.md) |
| Recherche, preuves et citations | [Recherche locale et sources](../RECHERCHE_LOCALE_SOURCES.md) |
| Taille des prompts et outils | [Prompts](../PROMPTS.md) · [Sept rôles](../../config/core/agents.yaml) |
| Préférences d’apprentissage approuvées | [Guide Apprendre](../fiches/05-apprendre.md) · [Fiche mentor dans le code](../../src/clawfedora/mentor.py) |
| Contrats d’évaluation (technique et pédagogique) | [Sept scénarios techniques](../EVALUATION_AGENTS.md) · [Dialogues pédagogiques /20](../EVALUATION_PEDAGOGIE.md) · [Jeux de tests](../../config/evals/) |
| Streaming expérimental | [SSE canary](../STREAMING_SSE_PREPARATION.md) |
| Justification des modèles | [Décision de modèle](../DECISION_MODELE.md) |
| Fichiers et responsabilités | [Architecture expliquée](../fiches/11-comment-ca-marche.md) · [Sécurité](../../SECURITY.md) |

Les fichiers YAML/JSON du dossier `config/` et le code de `src/` font foi lorsqu’une version, un plafond ou un chemin change. La documentation doit suivre **la même PR**.

[← Sommaire de la documentation](../README.md)
