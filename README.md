# Atelier IA local — Infrastructure & OPS

<p align="center">
  <img src=".github/social-preview.svg" alt="Atelier IA local — Infrastructure & OPS : un modèle Qwen, sept rôles, Fedora et Draw.io" width="100%">
</p>

[![CI](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml)
[![CodeQL](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml)
[![Fedora 44](https://img.shields.io/badge/Fedora-44-51A2DA?logo=fedora&logoColor=white)](https://fedoraproject.org/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)

**Une IA qui tourne sur son propre PC, pour discuter, apprendre le DevOps et mener des projets sans abonnement. Un cloud facultatif, borné à 25 € par mois, peut la compléter.**

## Pourquoi ce projet

Projet personnel. Les abonnements à Claude et ChatGPT sont une dépense récurrente, alors que la machine disponible peut faire tourner un modèle d'IA : Ryzen 7 7700, 48 Go de RAM et Intel Arc B580 de 12 Go, sous Fedora 44. Ce projet l'utilise pour les échanges de tous les jours.

Il accompagne aussi un parcours : passer de l'administration systèmes et réseaux au DevOps, côté déploiement et infrastructure. L'atelier est donc réglé pour expliquer, faire pratiquer et relire, pas seulement pour donner des réponses.

## Ce qu'il fait

| Usage | Interface |
|---|---|
| Discuter et poser n'importe quelle question | Open WebUI, `http://127.0.0.1:3000` |
| Apprendre avec un mentor qui part des acquis de l'utilisateur | Open WebUI ou l'atelier |
| Mener un projet avec sept rôles spécialisés | Atelier Projets, `http://127.0.0.1:18890` |
| Piloter un projet de la création à la livraison, avec confirmations humaines | Open WebUI ou Atelier Projets |
| Joindre des PDF, Office, archives, code et images avant l'analyse | Open WebUI ou Atelier Projets |
| Pratiquer en mode guidé, soumettre ses fichiers et recevoir un retour | Open WebUI ou Atelier Projets |
| Dicter une question et écouter une réponse, sans service vocal cloud | Open WebUI, Whisper + TTS locaux |
| Obtenir de vrais fichiers : Markdown, PDF, DOCX, YAML, Terraform, schémas Draw.io | Les deux |

En local, un seul modèle, **Qwen 3.5 9B**, tourne sur la carte graphique avec Ollama. **OpenClaw** lui donne sept rôles : mentor, recherche, architecte, DevOps, sécurité, rédacteur et auditeur. Ce sont sept jeux de consignes pour le même modèle, pas sept IA en mémoire.

![Deux interfaces, un même moteur](docs/diagrams/atelier-architecture.svg)

## Local d'abord, cloud sur demande

Le cloud (DeepSeek V4.1 Flash par OpenRouter) est **facultatif** et désactivé tant que tu ne l'actives pas.

- **Il ne s'active que si le filtre de confidentialité et le contrôle du budget fonctionnent ensemble.**
- **Tout passe par une passerelle locale** qui filtre ce qui part (historique et résultats d'outils compris), compte chaque appel facturé et refuse au plafond de **25 € réels par mois**.
- **Dans le chat**, tu choisis le modèle « · cloud » pour des questions publiques, et « · local » pour le reste.
- **Dans l'atelier**, chaque projet demande ton accord, et il se met en pause plutôt que de basculer en local sans te le dire.

Détail, activation et limites : [Le cloud, facultatif](docs/fiches/12-cloud.md). Pourquoi DeepSeek pour les tâches complexes et Qwen pour le local : [Quel modèle pour expliquer](docs/DECISION_MODELE.md).

## Ce qu'il ne fait pas

- **Le PC cible reste à valider** : l'intégration est testée automatiquement, mais les performances réelles de la B580, Whisper, Open WebUI et du vrai OpenRouter doivent encore être mesurées sur Fedora.
- Les sources d'un projet sont figées dès que l'analyse commence. Ajouter une nouvelle source impose de revenir au cadrage ou de créer un nouveau projet ; une pièce jointe ne modifie jamais silencieusement un projet déjà analysé.
- Les images restent locales : elles peuvent être ingérées et lues par Qwen, mais ne partent pas vers DeepSeek tant que le filtre de confidentialité ne sait pas inspecter leur contenu.
- En local, Qwen 9B n'égale pas un grand modèle cloud sur les tâches longues. DeepSeek V4.1 Flash est la route de capacité : contexte cloud disponible jusqu'à 1M de tokens, sortie 32K et raisonnement `xhigh`, toujours derrière le filtre et le budget.
- Il n'exécute rien sur le PC. Les rôles proposent du code et des fichiers ; c'est l'utilisateur qui les exécute.
- Il n'est accessible que depuis ce PC. Hors cloud, aucune conversation ni aucun projet n'en sort (seule la recherche Web des rôles interroge le Web) ; avec le cloud, seul ce que le filtre laisse passer part, et seulement pour ce que tu as choisi d'y envoyer. Le filtre arrête les secrets, pas un contenu confidentiel qui n'en a pas l'allure.

## Prérequis

- Fedora 44 Workstation (GNOME, Wayland), SELinux en `Enforcing`, pare-feu actif ;
- une carte graphique Intel Arc B580 (pilote `xe`), UEFI avec Resizable BAR ;
- environ 15 Go libres sous `/srv` pour le modèle et les outils.

Les vérifications détaillées sont dans [Installer](docs/fiches/01-installer.md). Le cloud n'exige rien de plus au départ : il s'ajoute plus tard, si tu le veux.

## Démarrer

Sur Fedora 44, depuis le compte utilisateur habituel (jamais en root) :

```bash
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd OPENCLAW_LOCAL_FEDORA
./menu.sh --action install            # aperçu, ne modifie rien
./menu.sh --action install --apply
./menu.sh --action context-probe --apply   # la carte suit-elle, et à quelle vitesse ?
./menu.sh --action webui-install --apply
```

`./menu.sh --help` liste toutes les actions.

## Documentation

**[Le guide](docs/GUIDE.md)** donne la trame et renvoie vers une fiche par sujet :

| | |
|---|---|
| [Installer](docs/fiches/01-installer.md) | [Rôles et outils](docs/fiches/07-roles-et-outils.md) |
| [Premier essai](docs/fiches/02-premier-essai.md) | [Réglages](docs/fiches/08-reglages.md) |
| [Discuter](docs/fiches/03-discuter.md) | [Entretenir](docs/fiches/09-entretenir.md) |
| [Atelier Projets](docs/fiches/04-atelier-projets.md) | [Dépanner](docs/fiches/10-depanner.md) |
| [Apprendre](docs/fiches/05-apprendre.md) | [Comment ça marche](docs/fiches/11-comment-ca-marche.md) |
| [Fichiers et schémas](docs/fiches/06-fichiers-et-schemas.md) | [Le cloud, facultatif](docs/fiches/12-cloud.md) |
| [Test de fumée Open WebUI](docs/SMOKE_TEST_WEBUI.md) | [Quel modèle pour expliquer](docs/DECISION_MODELE.md) |
| [Plan : tout faire depuis Open WebUI](docs/PLAN_INTEGRATION_WEBUI.md) | |

L'ancien PDF illustré de pré-intégration n'est plus la référence : le guide Markdown, les fiches et le test de fumée décrivent désormais l'architecture actuelle.

## État

Le logiciel passe ses tests automatiques, y compris avec le vrai OpenClaw. Il n'a pas encore tourné sur le PC cible : la vitesse, la tenue en mémoire vidéo et la qualité des réponses restent à mesurer. Le cloud n'a jamais été essayé avec le vrai OpenRouter : seul un faux fournisseur a servi aux tests. Détail dans [STATUS.md](STATUS.md).

Versions utilisées : OpenClaw 2026.9.8, Ollama 0.35.1, Open WebUI v0.11.4 (image slim). Elles sont fixées dans `config/` et ne se mettent pas à jour seules.

Historique des versions : [CHANGELOG](CHANGELOG.md). Règles de conduite : [CODE_OF_CONDUCT](CODE_OF_CONDUCT.md). Contribuer : [CONTRIBUTING](CONTRIBUTING.md). Sécurité : [SECURITY](SECURITY.md).

Licence [MIT](LICENSE). Le nom technique du dépôt reste `OPENCLAW_LOCAL_FEDORA`.
