# Atelier IA local — Infrastructure & OPS

<p align="center"><img src=".github/social-preview.svg" alt="Atelier IA Fedora : Qwen et Ornith locaux, sept rôles OpenClaw" width="100%"></p>

[![CI](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml)
[![CodeQL](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml)
[![Fedora 45](https://img.shields.io/badge/Fedora-45-51A2DA?logo=fedora&logoColor=white)](https://fedoraproject.org/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)

**Un atelier IA personnel pour comprendre, préparer, auditer et documenter des projets DevOps sur Fedora.** Les sept agents OpenClaw utilisent **uniquement Ollama en local** : **Qwen 3.5 9B** pour six rôles d'analyse/pédagogie et **Ornith 1.5 9B** pour l'ingénieur DevOps. **OpenRouter est retiré de la configuration active** : aucune facturation API ni bascule automatique vers un modèle distant. Les actions sensibles restent soumises aux règles de validation ; les agents ne disposent pas encore d'un shell autonome général.

[Découvrir](docs/GUIDE.md) · [Tester en Live USB](docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md) · [Installer](docs/INSTALLATION_SIMPLE_FEDORA45.md) · [Documentation](docs/README.md) · [État du projet](STATUS.md)

> **En qualification : le PC cible reste à valider.** Les défauts relevés par l'audit du 27 octobre sont corrigés et testés en CI ([audit et corrections](docs/AUDIT_SOURCE_2026_10_27.md)). Le projet n'a pas encore tourné sur le PC : la [liste de contrôle de réception](docs/RECEPTION_ETAPE3.md) décrit cette campagne.

## État en un coup d'œil

« Implémenté » signifie présent dans le code ; ce n'est pas « vérifié sur le PC ». Le détail et les dates sont dans [STATUS](STATUS.md).

| Élément | Avancement | Contrôle | Preuve et portée |
| --- | --- | --- | --- |
| Code, règles et tests automatisés | Implémenté | Vérifié en CI (instantané du 3 novembre) et en local (9 novembre) | [STATUS](STATUS.md) ; un test réussi n'est pas un essai sur Fedora |
| Installation et réception sur le PC (Fedora 45, Intel Arc B580) | À faire | Non vérifié | [Liste de contrôle de réception](docs/RECEPTION_ETAPE3.md) |
| Qwen et Ornith locaux : débit, VRAM, contexte 32K | Migration en PR | À mesurer sur la B580 | [Architecture locale](docs/ARCHITECTURE_LOCALE_QWEN_ORNITH.md) |
| OpenRouter / passerelle cloud | Retiré des routes actives | Contrats et CI de migration en vérification | [Retrait et reprise](docs/ARCHITECTURE_LOCALE_QWEN_ORNITH.md) |

## Ce que tu peux faire

- **Discuter et apprendre** : poser une question ou analyser de petits fichiers sans créer de projet.
- **Préparer une infrastructure** : architectures, configurations, scripts, runbooks et points de contrôle.
- **Organiser un projet** : sources, plan, tâches, validations humaines et livrables persistants.
- **Rédiger et vérifier** : Markdown, exports PDF/DOCX/ODT, schémas Draw.io et audits de cohérence.

Les sept rôles n'ont pas de shell libre sur l'hôte. Le seul outil d'exécution proposé est un validateur DevOps Podman hors réseau, limité à une copie de la proposition et à une image approuvée manuellement. Les actions sensibles comme la livraison restent soumises à ta validation. L'atelier ne déploie pas automatiquement l'infrastructure préparée.

## Une seule interface graphique principale

**Atelier IA Fedora** — `http://127.0.0.1:18890` : quatre espaces
dans une même application locale : **Discussions**, **Projets**, **GitHub**
et **Notion**. Les conversations utilisent les sept rôles OpenClaw et
les deux modèles locaux fournis par Ollama. `./menu.sh` reste l'outil de maintenance
en terminal, et non une seconde interface graphique.

Le conteneur **Open WebUI** n'est conservé que pour la transition et
la récupération de ses anciens chats ; il n'est plus requis pour créer
une discussion dans l'Atelier. Aucune suppression automatique de données.
[Architecture, installation et limites du chat natif](docs/ATELIER_UNIQUE_CHAT_OLLAMA.md).

Les [améliorations des sept agents et outils documentaires](docs/METHODES_V26_CLAWFEDORA.md)
renforcent les schémas Draw.io, la relecture GitHub/Notion et les propositions
de recette opérationnelle. Elles n'ajoutent aucun Skill et n'autorisent
aucune exécution de commande par un modèle.

Pour les projets longs, une nouvelle discussion liée au même projet retrouve un
résumé des jalons et des décisions acceptées. La commande `!continuer` montre
les prochaines étapes possibles et vérifie les reçus sans relancer d'agent ;
les conversations privées ne sont pas fusionnées.
[Reprise des projets longs](docs/PROJETS_LONGUE_DUREE.md).

Le streaming natif du Mentor sans projet est disponible uniquement via un canary
local explicite, sans changer la route stable des autres agents et projets.
[Streaming des discussions natives](docs/STREAMING_DISCUSSIONS_NATIVES.md).

Une page [Performances](docs/PERFORMANCES_QWEN_ORNITH.md) compare les relevés
réels de Qwen et Ornith (8K, 16K, 32K) sans exécuter de modèle en ouvrant
l'interface. Le rapport privé exige un benchmark explicitement lancé sur Fedora.
Les [profils GPU expérimentaux réversibles](docs/PROFILS_GPU_EXPERIMENTAUX.md)
permettent de préparer et comparer Flash Attention et le cache KV q8_0 sans
changer le contexte de production ni activer un candidat par défaut.


Les projets restent indépendants, avec un seul moteur exécutant une génération
à la fois. Les commandes humaines et approbations passent par le moteur OpenClaw
déjà configuré. Le diagnostic du PC est **en lecture seule** par défaut.

## Commencer

Le parcours complet est : essai facultatif en Live USB, installation, contrôle rapide, puis réception. Chaque étape a son guide ; ce README ne garde que le premier geste.

### 1. Facultatif : essayer Fedora sur la machine

Un essai préalable possible utilise **Fedora 45 Workstation / GNOME 51 / Wayland en Live USB**. Le contrôle autonome observe le matériel sans installer l'atelier :

```bash
# Depuis une copie du dépôt dans la session Live, sans sudo
bash scripts/linux/16_live_usb_preflight.sh
```

Suivre le [guide Live USB](docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md) pour préparer le média et conserver le rapport. **Un résultat favorable préqualifie le matériel ; il ne valide pas encore OpenClaw, Qwen ou WebUI.** La date de publication de Fedora doit être vérifiée sur le site officiel avant de choisir l'ISO.

### 2. Installer l'atelier

Sur Fedora installé, suivre le [guide d'installation](docs/INSTALLATION_SIMPLE_FEDORA45.md), qui regroupe la préparation du stockage, le précontrôle, l'installation et l'ouverture de l'Atelier natif (WebUI facultatif pour les anciens chats). Le runtime et ses projets utilisent **`/data/IA/Openclaw/`**, sur le disque secondaire EXT4.

**Machine cible :** Ryzen 7 7700, 48 Go de RAM, Intel Arc B580 12 Go. Fedora est le système hôte du projet IA ; l'Atelier natif se lance comme service utilisateur. Open WebUI sous Podman reste facultatif pour la transition. Aucune installation de Rocky Linux n'est nécessaire. [Stockage et prérequis](docs/STOCKAGE_DATA.md).

### 3. Vérifier, puis réceptionner

Après installation de l'Atelier natif, depuis le dépôt :

```bash
./menu.sh --action quick-check
```

Si le contrôle affiche `RECEPTION=READY_FOR_FIRST_PROJECT`, poser une vraie question dans l'espace Discussions et créer un petit projet de test, puis suivre la [liste de contrôle de réception](docs/RECEPTION_ETAPE3.md). Ce qui reste à prouver est indiqué dans [STATUS](STATUS.md).

**Cas métier étudié :** [OpsDesk et ses 13 exercices InfraOps](docs/CAS_USAGE_INFRAOPS_OPSDESK.md).
La répartition des agents tient compte de la différence entre VM créées par
Terraform/libvirt, configuration Ansible de Rocky, service Docker Compose,
copie d'essai K3s et preuve de restauration. Les modèles sont qualifiés
sur des scénarios synthétiques correspondants, sans solutions toutes faites
aux exercices personnels.

## Importations GitHub et Notion (opt-in, lecture seule)

Le projet peut maintenant ingérer un **instantané GitHub lié à un SHA complet**
ou les **pages Notion explicitement choisies**, avec empreintes et vérification
des sources. GitHub demeure la référence du code et du portfolio ; Notion
reste le centre des cours, exercices, notes et progression. Les notes
Notion importées sont **locales uniquement** : pas d'inférence distante par OpenRouter ; aucune mise à jour automatique du suivi Notion.

`clawfedora-sources` démarre en mode simulation et ne lit les API qu'avec
`--apply`. Ce n'est **pas encore une synchronisation en direct depuis le
chat**, ni un accès aux VM Rocky. [Mode d'emploi et limites](docs/INTEGRATION_GITHUB_NOTION.md).

## Documentation Notion de qualité wiki

L'atelier dispose d'une [charte visuelle et éditoriale universelle](docs/NOTION_WIKI_DESIGN_SYSTEM.md)
et de [gabarits de pages Notion](templates/notion/accueil-wiki.md). Les sept agents
actuels se répartissent architecture, rédaction, vérification technique
GitHub et audit documentaire. Un rendu premium ne transforme ni les
notes personnelles ni les sorties illustratives en preuves réelles.
Le [module de révision Notion ciblée](docs/NOTION_CONTROLLED_WRITES.md)
permet de préparer un diff puis de modifier **un bloc texte simple**
existant après approbation exacte. Le [lot multi-blocs contrôlé](docs/NOTION_MULTI_BLOCK.md)
étend ce principe à plusieurs blocs simples d'une même page, avec inventaire
et arrêt en cas de conflit. Le [panneau Notion local](docs/NOTION_DASHBOARD.md)
permet de les examiner et d'approuver les révisions depuis le navigateur.
Le [mode texte enrichi](docs/NOTION_RICH_TEXT.md) ajoute une correction par
segment pour les encadrés, listes et titres formatés, sans réécrire les autres
segments, leurs styles ou leurs liens. Les [tableaux et illustrations existants](docs/NOTION_TABLES_IMAGES.md)
peuvent aussi recevoir des modifications textuelles ciblées (cellule ou légende),
sans redimensionner les tableaux ni remplacer les fichiers image. Ni synchronisation du suivi ni écriture autonome
du modèle n'est autorisée.

## Mes projets dans Open WebUI

La [gestion des dossiers de projets natifs](docs/OPENWEBUI_NATIVE_PROJECT_FOLDERS.md)
permet d'afficher les projets du registre ClawFedora dans la barre latérale
Open WebUI et de classer explicitement une conversation dans son dossier.
L'historique du chat demeure dans Open WebUI ; les sessions terminal natives
OpenClaw ne sont **pas** fusionnées ou importées automatiquement.

## Interface locale modernisée

Les trois espaces **Projets, GitHub et Notion** partagent une
[navigation, des onglets et un design system responsive](docs/WORKBENCH_UI_DESIGN.md).
La présentation claire/sombre, les cartes et les états de revue sont
modernisés sans changer les permissions ni les règles d'approbation.
L'application Open WebUI de discussion sur le port 3000 est distincte.
La [recette visuelle réelle](docs/validation/VISUAL_RECEPTION_NATIVE.md)
sur Fedora reste nécessaire.

## GitHub depuis l'atelier et les discussions

Le [panneau GitHub local et ses commandes de discussion](docs/GITHUB_CHAT_DASHBOARD.md) permettent de préparer un dépôt, lire ses réglages, auditer des livrables et proposer une PR en brouillon après approbation du SHA exact du plan. Les opérations de publication depuis Open WebUI sont **des commandes que l'utilisateur tape**, pas des décisions autonomes du modèle.

### Préparer la réception graphique réelle

Le [protocole de captures et de revue humaine](docs/validation/VISUAL_RECEPTION_NATIVE.md)
permettra de vérifier les panneaux locaux, les pages Notion réelles et
les README GitHub en clair/sombre et sur largeur mobile. Il utilise
un navigateur optionnel, conserve ses captures privées hors dépôt et
ne déclare jamais la qualité graphique certifiée par une simple CI verte.
La réception sur Fedora et sur les comptes réels reste à effectuer.

## Création de dépôts et protection GitHub

La [configuration distante GitHub](docs/GITHUB_REMOTE_SETUP.md) ajoute des aperçus hors ligne pour créer un dépôt privé et vérifier les protections, puis des opérations sous approbation explicite. Aucune création distante n'est déclenchée par la simple consultation du README.

## Publication GitHub après validation humaine

L'[atelier de création et de PR brouillon](docs/GITHUB_PUBLICATION_WORKFLOW.md)
prépare des structures locales réutilisables et peut publier une proposition
dans un dépôt GitHub **existant**, avec un SHA de base vérifié et une
autorisation explicite. La fusion, les droits de dépôt et la publication
en tant que dépôt public restent sous contrôle humain. Les agents ne
prétendent pas avoir validé le rendu GitHub ni Fedora.

## Qualité des dépôts GitHub

La [charte GitHub réutilisable](docs/GITHUB_REPOSITORY_DESIGN_SYSTEM.md)
et ses [sept modèles](templates/github/readme-projet.md)
aident à construire des README lisibles, des architectures sourcées,
des preuves datées et des procédures reproductibles.
`clawfedora-github-audit` inventorie localement les documents,
liens et diagrammes d'un projet ou d'un snapshot importé, en lecture seule.
Il n'exécute **ni tests applicatifs ni commandes de déploiement** et ne
crée aucune PR.

## Priorité métier : deux modèles locaux, sept rôles

L'atelier conserve **Qwen 3.5 9B Q4_K_M** pour le mentor, la recherche, l'architecture, la sécurité, la rédaction et l'audit. **Ornith 1.5 9B Q4** est affecté à l'ingénieur DevOps pour Terraform, Ansible, Docker, Kubernetes, scripts et CI/CD. Les modèles sont chargés alternativement par Ollama (`OLLAMA_MAX_LOADED_MODELS=1`). Les projets et la mémoire restent sous contrôle du worker.

**OpenRouter, DeepSeek et Sol ne font plus partie du routage actif.** Le mode cloud, y compris les anciens appels de l'interface CLI, est refusé. Le retrait des clés du poste est une opération distincte et explicite (`./menu.sh --action local-retire-cloud --apply`) ; les journaux historiques ne sont pas effacés.

La recherche Web peut encore consulter Internet pour récupérer des *sources* si tu la laisses activée ; cela n'envoie pas les conversations à un fournisseur de modèle payant. Le [mode Web privé](docs/WEB_ACCESS_PRIVATE_MODE.md) désactive les outils Web.

[Architecture locale, choix des modèles et réception](docs/ARCHITECTURE_LOCALE_QWEN_ORNITH.md) · [Optimisations des projets longs](docs/PERFORMANCE_PROJETS_LONGS.md) · [Sécurité](SECURITY.md)

## Sept rôles, un même atelier

Mentor infrastructure/OPS · Expert recherche · Architecte solutions · Ingénieur DevOps · Ingénieur sécurité · Rédacteur pédagogique · Auditeur qualité.

Chaque rôle reçoit ses consignes et ses outils autorisés. [Découvrir leurs responsabilités](docs/fiches/07-roles-et-outils.md) · [Voir l'architecture](docs/fiches/11-comment-ca-marche.md).

## Ce qui vient d'où

L'atelier assemble des composants tiers et y ajoute son propre code. La distinction compte pour juger ce qui a été développé ici.

| Origine | Éléments | Rôle dans l'atelier |
| --- | --- | --- |
| **Composants tiers**, versions épinglées | OpenClaw 2026.10.5, Ollama 0.40.6, Open WebUI 0.12.3 facultatif, modèles Qwen 3.5 9B et Ornith 1.5 9B | Agents, inférence locale, interface de chat, modèles |
| **Ce dépôt** | Paquet Python `clawfedora` (`src/`), scripts d'installation et de maintenance (`scripts/`), consignes des sept rôles (`agents/`), politiques (`config/`), plugins (`plugins/`), tests (`tests/`), documentation (`docs/`) | Moteur de projets, contrôles locaux, installation, pédagogie et retrait de l'ancienne passerelle |

Les versions exactes sont dans [`config/runtime_versions.yaml`](config/runtime_versions.yaml) et expliquées dans [les références techniques](docs/reference/README.md).

## Limites connues

- **Pas encore essayé sur le PC cible** : toutes les mesures réelles (GPU, WebUI dans le navigateur, voix, restauration) restent à faire.
- **Pas de déploiement autonome** : les fichiers proposés par les agents ne prouvent pas qu'un Terraform ou un Ansible a réussi.
- **Usage prévu : une personne, sur son propre PC.** L'atelier n'est pas conçu pour être exposé sur un réseau ; les sauvegardes locales ne sont pas chiffrées ([Sécurité](SECURITY.md)).
- **Qualité des réponses non mesurée** : la qualité de Qwen et Ornith sur OpsDesk reste à qualifier avec des preuves réelles ([Évaluation pédagogique](docs/EVALUATION_PEDAGOGIE.md)), sans note automatique.

## Trois points à retenir

1. Les **deux modèles sont locaux uniquement**, sans inférence payante ni route de secours OpenRouter.
2. Le modèle propose, le moteur encadre, **tu valides et tu exécutes**.
3. Le code est testé automatiquement, mais **le PC Fedora n'a pas encore réceptionné l'atelier**.

## Recette globale de réception

La [recette actuelle de l’Atelier natif](docs/RECETTE_GLOBALE.md) centralise
les contrôles logiciels, le précontrôle du poste et les preuves à recueillir.
Lancer `./menu.sh --action acceptance-plan` pour afficher le parcours sans
inférence, ou `acceptance-source` pour vérifier les contrats du dépôt.
Les essais matériels restent distincts et nécessitent Fedora installé.

## Documentation

| Besoin | Guide |
| --- | --- |
| Prendre en main le chat et les projets | [Discussion](docs/fiches/03-discuter.md) · [Atelier Projets](docs/fiches/04-atelier-projets.md) |
| Produire ou importer des documents | [Fichiers, exports et schémas](docs/fiches/06-fichiers-et-schemas.md) |
| Juger la qualité des explications | [Évaluation pédagogique](docs/EVALUATION_PEDAGOGIE.md) |
| Diagnostiquer ou préparer la réception | [Dépannage](docs/fiches/10-depanner.md) · [Validation](docs/validation/README.md) |
| Comprendre les versions et protections | [Références techniques](docs/reference/README.md) · [État et limites](STATUS.md) |

## Informations pratiques

Licence [MIT](LICENSE) · Auteur : [mathiasseguincadiche](https://github.com/mathiasseguincadiche) · [Contribuer](CONTRIBUTING.md) · [Historique](CHANGELOG.md) · [Signaler une faille](SECURITY.md#signaler-un-problème) · [Code de conduite](CODE_OF_CONDUCT.md)
