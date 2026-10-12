# Atelier IA local — Infrastructure & OPS

<p align="center"><img src=".github/social-preview.svg" alt="Atelier IA Fedora : sept rôles, un moteur, des projets sous contrôle humain" width="100%"></p>

[![CI](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml)
[![CodeQL](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml)
[![Fedora 44](https://img.shields.io/badge/Fedora-44-51A2DA?logo=fedora&logoColor=white)](https://fedoraproject.org/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)

> **En bref :** une IA personnelle sous Fedora pour **comprendre**, **concevoir**, **préparer** et **faire relire** des travaux Linux/DevOps. Sept rôles spécialisés, des documents téléchargeables et **aucun déploiement automatique sur le PC**.

**Tu découvres le projet ?** Commence par [le guide](docs/GUIDE.md), puis suis [l'exemple d'un projet DevOps](docs/EXEMPLE_PARCOURS_DEVOPS.md). Pour savoir ce qui a été réellement testé, consulte [STATUS.md](STATUS.md).

## À quoi sert-il concrètement ?

L'atelier transforme une demande (« explique Terraform », « prépare mon pipeline », « aide-moi à diagnostiquer un service ») en **explications, décisions, fichiers ou rapports argumentés**. Il est pensé pour progresser depuis Linux et les réseaux vers le métier DevOps infrastructure/OPS.

| Ton besoin | Ce que tu obtiens |
|---|---|
| Comprendre une notion | Une réponse directe, un exemple et les points à vérifier |
| Faire un choix d'architecture | Une comparaison, les flux, les compromis et, si utile, un Draw.io |
| Préparer un déploiement | Des scripts, configurations, procédures et un retour arrière **à tester** |
| Vérifier la sécurité | Des risques priorisés, des preuves disponibles et des corrections proposées |
| Préparer un livrable | Un Markdown modifiable, éventuellement exporté en PDF/DOCX |
| Mener un travail long | Un plan approuvé, des tâches attribuées, des contrôles et un dossier final |

Le **mode direct** fournit une explication ou une proposition complète. Les exercices guidés sont **facultatifs et soumis à ton choix**, jamais obligatoires.

## Les sept agents : des métiers, pas sept modèles

Chaque rôle possède ses **consignes**, son **espace de travail** et une **liste d'outils limitée**. Tous partagent **Qwen 3.5 9B Q4_K_M** en local via Ollama ; un rôle de plus ne charge pas un nouveau modèle. Le moteur appelle les spécialistes utiles, **un à la fois**, plutôt que de les laisser agir librement.

| Rôle | Sa question | Ce qu'il produit |
|---|---|---|
| **Mentor infrastructure/OPS** (défaut) | « Que veux-tu comprendre ou accomplir ? » | Explications, cadrage, plan court |
| **Expert recherche** | « Qu'est-ce qui est confirmé et récent ? » | Sources datées, notes et réserves |
| **Architecte solutions** | « Quelle solution convient et pourquoi ? » | Décisions (ADR), flux, Draw.io/SVG |
| **Ingénieur DevOps** | « Comment le construire et le vérifier ? » | Terraform, Ansible/YAML, scripts, CI/CD, runbooks |
| **Ingénieur sécurité** | « Qu'est-ce qui peut mal tourner ? » | Analyse de risques, contrôles défensifs |
| **Rédacteur pédagogique** | « Comment le rendre clair et transmissible ? » | Guide, documentation, PDF/DOCX |
| **Auditeur qualité** | « Quels critères sont réellement prouvés ? » | Rapport de vérification, écarts et limites |

**L'auditeur n'est pas un second modèle indépendant** : c'est une session séparée du même moteur. Aucun rôle n'a d'accès libre au terminal, ne déploie ton infrastructure ni ne décide à ta place.

→ [Comprendre le rôle, les outils, les limites et un exemple pour chacun](docs/fiches/07-roles-et-outils.md).

![Sept rôles, un moteur](docs/diagrams/atelier-roles.svg)

## Comment fonctionne l'ensemble ?

![Architecture : interfaces, contrôle, rôles, modèles et fichiers](docs/diagrams/atelier-architecture.svg)

**Lecture du dessin :** tu pars des deux interfaces, la demande rejoint le **pont de chat** ou le **moteur de projets**, puis **OpenClaw** applique les règles du rôle choisi. Le modèle répond via **Ollama/Qwen** ou, seulement sur choix explicite, via la **passerelle cloud/DeepSeek**. Le moteur contrôle les fichiers et demande tes validations.

1. **Tu demandes** une réponse dans Open WebUI ou crées un projet à étapes.
2. **Le système choisit le rôle** et verrouille la génération (une seule à la fois).
3. **OpenClaw fournit les consignes et outils autorisés** au modèle.
4. **Le modèle propose**, et les outils peuvent chercher des sources, contrôler une syntaxe ou produire des fichiers.
5. **Le collecteur et l'auditeur** contrôlent les sorties prévues dans un projet ; l'humain confirme les étapes sensibles.
6. **Tu vérifies et décides** : aucun code fourni n'est réputé exécuté.

→ [Explication pas à pas des composants, ports, flux, sécurité et cas d'échec](docs/fiches/11-comment-ca-marche.md).

## Deux interfaces, un moteur partagé

| Interface | Sur le PC Fedora | Ce qu'elle permet |
|---|---|---|
| **Open WebUI** | `http://127.0.0.1:3000` | Chat, choix du rôle, fichiers, dictée, commandes `!` ; trois boutons rapides **en lecture seule** |
| **Atelier Projets** | `http://127.0.0.1:18890` | Créer, cadrer, approuver, suivre les tâches, vérifier et livrer via le tableau de bord |

**Précision :** Open WebUI n'a pas encore tous les contrôles de projet en boutons. Les opérations avancées utilisent les commandes textuelles ou le tableau de bord. Le chat local permet aussi d'analyser de petits fichiers texte/code **sans créer de projet** (4 fichiers, 12 000 octets cumulés) ; les PDF, Office et images suivent l'ingestion contrôlée d'un projet. [Détails des fichiers](docs/fiches/06-fichiers-et-schemas.md).

## Modèle local et cloud facultatif

- **Local (par défaut)** : Qwen 3.5 9B sur Intel Arc B580, sans envoi du chat à un modèle distant.
- **Cloud (sur activation)** : DeepSeek V4.1 Flash par OpenRouter, derrière un filtre de secrets et un contrôle de budget de **25 € par mois**. L'estimation du journal n'est pas la facture : crédits prépayés, limite de clé et relevé du fournisseur restent nécessaires.
- **Pas de bascule cachée du local vers le cloud.** Un projet exige son accord propre. Une recherche Web demandée à un agent peut en revanche interroger Internet, même lorsque le modèle est local.

→ [Cloud : confidentialité, budget, limites et activation](docs/fiches/12-cloud.md).

## Démarrer sur Fedora

Cible : **Fedora 44**, Ryzen 7 7700, 48 Go de RAM, Intel Arc B580 12 Go. Installation sans root, avec SELinux actif.

```bash
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd OPENCLAW_LOCAL_FEDORA
./menu.sh --action install                  # aperçu sans modification
./menu.sh --action install --apply
./menu.sh --action health
./menu.sh --action check-gpu
./menu.sh --action context-probe --apply    # performances à mesurer
./menu.sh --action webui-install --apply
```

→ [Préparer l'installation](docs/fiches/01-installer.md) · [Vérifier le premier essai](docs/fiches/02-premier-essai.md).

## Limites : ne pas confondre « codé » et « prouvé »

**Le PC cible reste à valider :** le projet n'a pas encore tourné sur le PC cible dans le cadre des essais de réception documentés. Accélération B580, vraie interface et uploads Open WebUI, voix, sauvegarde/restauration et appels réels OpenRouter restent à qualifier. Les réponses du chat arrivent **en bloc**, la carte ne traite qu'une génération à la fois, et les fichiers proposés ne sont **pas** des déploiements validés. La version déployée reste **Open WebUI 0.11.4** : le canary 0.12.0 est un essai isolé, pas une migration.

Les tests automatiques ne prouvent pas un résultat sur ton matériel. Voir [état précis](STATUS.md), [test de fumée](docs/SMOKE_TEST_WEBUI.md) et [plan de qualité](docs/PLAN_QUALITE_2026.md).

## Où lire la suite ?

| Découvrir | Agir et approfondir |
|---|---|
| **[Guide de découverte](docs/GUIDE.md)** | [Discuter et choisir un rôle](docs/fiches/03-discuter.md) |
| **[Exemple concret de bout en bout](docs/EXEMPLE_PARCOURS_DEVOPS.md)** | [Conduire un projet](docs/fiches/04-atelier-projets.md) |
| **[Les sept rôles et leurs outils](docs/fiches/07-roles-et-outils.md)** | [Apprendre sans exercice imposé](docs/fiches/05-apprendre.md) |
| **[Architecture expliquée](docs/fiches/11-comment-ca-marche.md)** | [Fichiers et Draw.io](docs/fiches/06-fichiers-et-schemas.md) |
| [Règles et paramètres](docs/fiches/08-reglages.md) | [Entretenir](docs/fiches/09-entretenir.md) · [Dépanner](docs/fiches/10-depanner.md) |
| [Cloud facultatif](docs/fiches/12-cloud.md) | [STATUS](STATUS.md) · [CHANGELOG](CHANGELOG.md) |

Contribution : [CONTRIBUTING](CONTRIBUTING.md) · Sécurité : [SECURITY](SECURITY.md) · Licence : [MIT](LICENSE).

**À retenir : l'IA explique et propose ; le moteur contrôle et trace ; l'humain vérifie et décide.**
