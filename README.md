# Atelier IA hybride — Infrastructure & OPS

<p align="center"><img src=".github/social-preview.svg" alt="Atelier IA hybride Fedora : Qwen local et DeepSeek cloud, sept rôles sous contrôle humain" width="100%"></p>

[![CI](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml)
[![CodeQL](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml)
[![Fedora 45](https://img.shields.io/badge/Fedora-45-51A2DA?logo=fedora&logoColor=white)](https://fedoraproject.org/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)

> **En bref :** un **atelier IA hybride** sous Fedora : **Qwen 3.5 9B en local** pour l'autonomie et la confidentialité, **DeepSeek V4.1 Flash dans le cloud** pour les analyses DevOps difficiles et les contextes volumineux. **OpenClaw coordonne sept rôles spécialisés** avec des outils et des garde-fous communs. Aucun déploiement automatique sur le PC.

> **Confidentialité des recherches :** Qwen fonctionne localement, mais les outils `web_search`/`web_fetch` peuvent contacter Internet. Un [mode Web privé explicite](docs/WEB_ACCESS_PRIVATE_MODE.md) permet de désactiver leurs permissions pour les sept agents ; le basculement nécessite une application de configuration et un redémarrage vérifiés. Ce mode ne désactive pas automatiquement la route DeepSeek cloud.

## Le principe : deux moteurs complémentaires pour travailler efficacement

| | **Qwen local — autonomie** | **DeepSeek cloud — capacité ciblée** |
|---|---|---|
| **Pourquoi le choisir ?** | Travail quotidien, confidentialité, demandes bornées, accès au modèle sans facturation API | Problèmes complexes où un modèle plus puissant peut réduire les erreurs, les itérations et le temps de reprise |
| **Exemples DevOps** | Comprendre une commande Linux, expliquer un petit YAML, préparer un runbook court, relire une configuration privée | Comparer une architecture Azure/Rocky, raisonner sur plusieurs fichiers Terraform/Ansible, analyser un échec de pipeline difficile, auditer un ensemble public complexe |
| **Contexte configuré** | 32 768 tokens ; réponse jusqu'à 4 096 tokens | Jusqu'à 1 048 576 tokens déclarés ; sortie jusqu'à 32 768 tokens |
| **Conditions** | Route par défaut via Ollama sur le PC Fedora | Route sélectionnée explicitement, activation du cloud, filtre/budget opérationnels, **accord du projet** si des documents de projet sont concernés |

**L'objectif n'est pas de dépenser du cloud à chaque question, ni de forcer un petit modèle local sur une mission trop difficile.** On choisit le moteur selon **complexité, volume, sensibilité, délai et coût**. DeepSeek est la **route de capacité prévue pour les tâches qui le justifient**, pas un secours automatique lorsque Qwen échoue. Son gain de précision, de pédagogie ou de rapidité doit encore être **mesuré sur des cas réels**, et non présumé.

**Conseil pratique sans IA :** `!modele` (ou le bouton **Quel modèle choisir ?** dans Open WebUI)
affiche des recommandations déterministes pour les tâches Linux, IaC, CI,
architecture et documents. Aucun historique n'est inspecté ni envoyé à Qwen
ou DeepSeek. Le conseil ne certifie jamais que des données peuvent sortir du PC.

**Réglage de l'effort DeepSeek :** en plus du choix local/cloud, trois profils
d'exécution **globaux et explicites** sont disponibles : `rapide` (low, 4K),
`equilibre` (medium, 8K) et `approfondi` (xhigh, 32K, défaut historique).
La commande `./menu.sh --action cloud-profile` affiche le profil courant ;
`./menu.sh --action cloud-set-profile --value equilibre --apply` le modifie
sous verrou worker. Aucun agent ne peut changer ce profil ; le budget,
la confidentialité et le fournisseur restent contrôlés par la passerelle.
Ce n'est **pas** encore un routage automatique par tâche.
[Procédure des profils cloud](docs/fiches/12-cloud.md).

**Fonctionnement actuel :** le choix du modèle est **manuel et explicite** dans le chat ; le cloud d'un projet couvre les étapes autorisées du projet après consentement, sans sélection automatique du « meilleur modèle » pour chaque tâche. La sécurité et le budget priment sur la performance : le filtre de secrets ne sait pas détecter toutes les informations confidentielles.

→ **[Lire la stratégie hybride et les critères de choix](docs/ARCHITECTURE_HYBRIDE.md)**.

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

Chaque rôle possède ses **consignes**, son **espace de travail** et une **liste d'outils limitée**. Le même rôle peut travailler avec **Qwen 3.5 9B local** ou **DeepSeek V4.1 Flash cloud**, après sélection et autorisation ; il n'existe pas de « septième IA » indépendante par agent. **Deux moteurs d'inférence, sept expertises métier**, et une seule génération à la fois. Le moteur appelle uniquement les spécialistes utiles, au lieu de les laisser agir librement.

| Rôle | Sa question | Ce qu'il produit |
|---|---|---|
| **Mentor infrastructure/OPS** (défaut) | « Que veux-tu comprendre ou accomplir ? » | Explications, cadrage, plan court |
| **Expert recherche** | « Qu'est-ce qui est confirmé et récent ? » | Sources datées, notes et réserves |
| **Architecte solutions** | « Quelle solution convient et pourquoi ? » | Décisions (ADR), flux, Draw.io/SVG |
| **Ingénieur DevOps** | « Comment le construire et le vérifier ? » | Terraform, Ansible/YAML, scripts, CI/CD, runbooks |
| **Ingénieur sécurité** | « Qu'est-ce qui peut mal tourner ? » | Analyse de risques, contrôles défensifs |
| **Rédacteur pédagogique** | « Comment le rendre clair et transmissible ? » | Guide, documentation, PDF/DOCX |
| **Auditeur qualité** | « Quels critères sont réellement prouvés ? » | Rapport de vérification, écarts et limites |

**L'auditeur n'est pas automatiquement indépendant du modèle qui a produit le travail** : il reçoit une session séparée, mais peut utiliser la même route Qwen ou DeepSeek que les autres rôles du projet. Aucun rôle n'a d'accès libre au terminal, ne déploie ton infrastructure ni ne décide à ta place.

→ [Comprendre le rôle, les outils, les limites et un exemple pour chacun](docs/fiches/07-roles-et-outils.md).

![Sept rôles, un moteur](docs/diagrams/atelier-roles.svg)

## Comment fonctionne l'ensemble ?

![Architecture : interfaces, contrôle, rôles, modèles et fichiers](docs/diagrams/atelier-architecture.svg)

**Lecture du dessin :** tu pars des deux interfaces, puis le pont ou le moteur de projets transmet la mission à **OpenClaw**. Le rôle peut utiliser **Qwen sur la B580** (voie locale) ou, **après autorisation**, **DeepSeek via la passerelle cloud/OpenRouter** (voie de capacité). Le collecteur vérifie les fichiers et les décisions sensibles restent humaines. Les deux routes ne sont pas équivalentes en confidentialité, en coût ni en capacité.

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
| **Open WebUI** | `http://127.0.0.1:3000` | Chat, choix du rôle, fichiers, dictée, cinq raccourcis de lecture, huit actions confirmées et trois formulaires (création, précisions, révision) |
| **Atelier Projets** | `http://127.0.0.1:18890` | Créer, cadrer, approuver, suivre les tâches, vérifier et livrer via le tableau de bord |

**Précision :** le code prévoit onze actions visuelles de projet :
huit transitions confirmées et trois formulaires de création, de réponse
aux précisions et de demande de révision. **Elles ne remplacent pas** les
vérifications du moteur ni les approbations à usage unique ; la révision
proposée par formulaire nécessite encore un code distinct avant tout
changement. Les soumissions de fichiers restent accessibles par commande.
L'affichage effectif de ces actions dans Open WebUI reste à qualifier
sur Fedora. Le streaming SSE est **préparé mais non activé** par défaut.
Les opérations non couvertes utilisent les commandes ou l'Atelier Projets. Le chat local permet aussi d'analyser de petits fichiers texte/code **sans créer de projet** (4 fichiers, 12 000 octets cumulés) ; les PDF, Office et images suivent l'ingestion contrôlée d'un projet. [Détails des fichiers](docs/fiches/06-fichiers-et-schemas.md).

## DeepSeek n'est pas une fonctionnalité secondaire

**Sa mission dans l'architecture :** prendre le relais **sur décision de l'utilisateur** lorsque le besoin dépasse les capacités pratiques du 9B local : raisonnement long, recherche contradictoire, audit multi-fichiers, planification d'infrastructure, génération ou revue de code complexe. L'intérêt attendu est une **meilleure qualité par tâche** avec moins d'allers-retours ; ce bénéfice doit être vérifié par des comparaisons réelles et ne justifie jamais un envoi sensible.

**Le parcours cloud est volontairement contrôlé :** OpenClaw → passerelle locale (`127.0.0.1:18892`) → filtre de confidentialité → réservation du budget → OpenRouter → **DeepSeek V4.1 Flash**. Le plafond configuré est **25 € par mois**, avec prépaiement, limite de clé et rapprochement du coût réel. Une recherche Web d'agent peut interroger Internet même en mode Qwen local.

**Pas de bascule cachée Qwen → DeepSeek.** Dans un projet, l'accord cloud porte sur le projet et ses sources ; il ne constitue pas un routage automatique par spécialité. Les outils disponibles dépendent du **rôle**, pas de la marque du modèle.

→ [Comprendre précisément les deux routes](docs/ARCHITECTURE_HYBRIDE.md) · [Activer et protéger le cloud](docs/fiches/12-cloud.md) · [Pourquoi DeepSeek](docs/DECISION_MODELE.md).

## Démarrer sur Fedora

**Architecture cible : Fedora est le système hôte du projet IA.** OpenClaw,
Ollama, les sept rôles, le moteur de projets, la passerelle cloud et les
données fonctionnent côté Fedora. Open WebUI est prévu en **conteneur
Podman rootless sur ce même Fedora**. DeepSeek est le seul moteur d'inférence
déporté (via OpenRouter et sur autorisation). **Aucune installation de Rocky
Linux, VM Rocky ou image Rocky n'est requise pour démarrer ou utiliser
l'atelier IA.** Une VM Rocky peut servir *indépendamment* aux exercices
DevOps de l'utilisateur ; elle ne fait pas partie de l'infrastructure
d'exécution de l'atelier.

Cible après la publication officielle : **Fedora 45 Workstation + GNOME 51 (Wayland)**, Ryzen 7 7700, 48 Go de RAM, Intel Arc B580 12 Go. Installation par l'utilisateur habituel (sudo ponctuel), avec SELinux Enforcing. **Au 14 octobre 2026, Fedora 45 est encore en bêta : la sortie stable est ciblée au 20 octobre, sous réserve des critères de publication.**

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

## Outil de validation DevOps facultatif — hors du cœur IA

La commande indépendante `clawfedora-lab` prépare des vérifications Terraform, Ansible, GitHub Actions, ShellCheck et Dockerfile dans un **conteneur rootless, offline et jetable**, sur une copie limitée du projet. Aucun agent ne peut la déclencher librement : c'est **toi** qui dois fournir une **image de validateurs déjà présente, épinglée par digest**, puis `--apply`.

**Cet outil optionnel ne fait pas fonctionner OpenClaw et n'exige pas Rocky Linux.**
Le validateur demande une **image OCI locale de confiance contenant les outils**,
quelle que soit la distribution de base ; sa provenance et les essais Podman
réels restent à qualifier. Ce chantier ne bloque **ni le streaming ni le
pilotage WebUI**. [Fonctionnement, commandes et protections](docs/LABORATOIRE_DEVOPS.md).

## Faire progresser l'atelier sans se raconter d'histoires

La nouvelle commande `clawfedora-evals --plan` prépare sept scénarios DevOps synthétiques — un par agent — que Qwen et DeepSeek pourront passer sur les mêmes critères. Le rapport de notes humaines `clawfedora-evals --report fichier.json` vérifie l'exhaustivité de la grille, **mais n'appelle pas les modèles et ne certifie pas les résultats**.

→ [Évaluation des sept agents](docs/EVALUATION_AGENTS.md) · [Programme d'amélioration 2026](docs/PROGRAMME_AMELIORATION_2026.md).

## Vérifier les preuves CI officielles

La commande indépendante `clawfedora-ci-proof` permet de consulter **le statut officiel
d'une exécution GitHub Actions ou GitLab CI publique liée à un commit exact**,
sans envoyer de jeton ni appeler un modèle IA. Elle évite de prendre une mention
« CI réussie » dans un texte pour une preuve suffisante.

**Elle vérifie uniquement le statut global de la CI** : ni déploiement, ni
rollback, ni fonctionnement réel du système. [Guide de vérification et limites](docs/PREUVES_CI_GITHUB_GITLAB.md).

## Limites : ne pas confondre « codé » et « prouvé »

**Le PC cible reste à valider :** le projet n'a pas encore tourné sur le PC cible dans le cadre des essais de réception documentés. Accélération B580, vraie interface et uploads Open WebUI, voix, sauvegarde/restauration et appels réels OpenRouter restent à qualifier. Les réponses du chat arrivent **en bloc**, la carte ne traite qu'une génération à la fois, et les fichiers proposés ne sont **pas** des déploiements validés. La première installation vise directement **Open WebUI 0.12.3-slim**, dont l'image téléchargée est figée au premier démarrage par un digest dans l'unité systemd ; il n'y a pas de migration depuis 0.11.4 sur un PC vierge.

Les tests automatiques ne prouvent pas un résultat sur ton matériel. Voir [état précis](STATUS.md), [test de fumée](docs/SMOKE_TEST_WEBUI.md) et [plan de qualité](docs/PLAN_QUALITE_2026.md).

## Où lire la suite ?

| Découvrir | Agir et approfondir |
|---|---|
| **[Guide de découverte](docs/GUIDE.md)** | **[Choisir Qwen ou DeepSeek](docs/ARCHITECTURE_HYBRIDE.md)** |
| **[Exemple concret de bout en bout](docs/EXEMPLE_PARCOURS_DEVOPS.md)** | [Conduire un projet](docs/fiches/04-atelier-projets.md) |
| **[Les sept rôles et leurs outils](docs/fiches/07-roles-et-outils.md)** | [Apprendre sans exercice imposé](docs/fiches/05-apprendre.md) |
| **[Architecture expliquée](docs/fiches/11-comment-ca-marche.md)** | [Fichiers et Draw.io](docs/fiches/06-fichiers-et-schemas.md) |
| [Règles et paramètres](docs/fiches/08-reglages.md) | [Entretenir](docs/fiches/09-entretenir.md) · [Dépanner](docs/fiches/10-depanner.md) |
| [Cloud facultatif](docs/fiches/12-cloud.md) | [STATUS](STATUS.md) · [CHANGELOG](CHANGELOG.md) |

Contribution : [CONTRIBUTING](CONTRIBUTING.md) · Sécurité : [SECURITY](SECURITY.md) · Licence : [MIT](LICENSE).

**À retenir : l'IA explique et propose ; le moteur contrôle et trace ; l'humain vérifie et décide.**
