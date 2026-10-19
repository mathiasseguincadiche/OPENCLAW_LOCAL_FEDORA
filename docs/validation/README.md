# Validation — parcours court et diagnostics facultatifs

## Réception minimale : une fois Fedora installé

Utiliser la procédure [Installation simple](../INSTALLATION_SIMPLE_FEDORA45.md), puis une seule commande :

```bash
./menu.sh --action quick-check
```

Elle vérifie les composants essentiels (montage `/IA`, courte génération Qwen locale, carte B580 utilisée, Gateway, WebUI et projets). En cas de `READY_FOR_FIRST_PROJECT`, **poser une vraie question dans WebUI et créer un premier projet**. Pas de benchmark ni de cloud nécessaires pour commencer.

## Quand approfondir ?

| Besoin réel | Contrôle spécialisé |
| --- | --- |
| La B580 chauffe, le contexte semble trop grand, la veille échoue | [Qualification Fedora 45 et GPU](../QUALIFICATION_FINALE_FEDORA.md) |
| WebUI, voix, boutons, streaming ou import de fichiers posent problème | [Réception WebUI avancée](../SMOKE_TEST_WEBUI.md) |
| Mesurer les réponses des sept agents | [Grille d’évaluation](../EVALUATION_AGENTS.md) |
| Vérifier la vision locale après activation volontaire | [Canary vision](../VISION_LOCALE_CANARY.md) |
| Comparer une CI à une preuve officielle | [Provenance GitHub/GitLab](../PREUVES_CI_GITHUB_GITLAB.md) |
| Exécuter des validateurs DevOps isolés (optionnel) | [Laboratoire DevOps](../LABORATOIRE_DEVOPS.md) |
| Vérifier les versions Python épinglées | [Verrou Python](../PYTHON_RUNTIME_LOCK.md) |
| Préqualification non persistante (non requise) | [Live USB](../LIVE_USB_FEDORA45_PREQUALIFICATION.md) |

**Ne pas confondre** : scripts simulés en CI, réception d’un logiciel sur le PC, conformité de l’infrastructure externe générée et coût réel OpenRouter. Seule une mesure sur la machine ou chez le fournisseur peut confirmer ces derniers points.

[← Sommaire de la documentation](../README.md)
