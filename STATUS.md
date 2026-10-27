# État du projet — Atelier IA hybride Fedora

**Référence auditée : 27 octobre 2026, commit `9e6322b` (PR #155).** L’état ci-dessous distingue ce qui est dans le code, ce que GitHub Actions vérifie et ce qui dépend encore du PC et des fournisseurs réels. **Une CI verte n’est pas une preuve d’exploitation sur Fedora.**

## Résumé vérifiable

| Dimension | Statut | Preuve ou limite |
| --- | --- | --- |
| **Code, règles et installation** | Contrats automatisés réussis ; défauts ouverts | Tests Python 3.12/3.13, ShellCheck, contrats Fedora 45 et validation OpenClaw native ; voir l’audit ci-dessous |
| **Référence de CI après fusion de la PR #155** | Succès | [Commit `9e6322b`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/9e6322b13a9af2d84baaf51b279e81919b73f94f), vérifié le 27 octobre : [dix jobs réussis](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/40119337966), 1 104 tests dans le job quality, couverture 85,80 %. Instantané daté, pas garantie des prochaines CI. |
| **Analyse statique** | Succès sur cette référence | [CodeQL après fusion](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/40119338118) réussi ; une nouvelle PR doit repasser ces contrôles |
| **Audit approfondi du 27 octobre** | Corrections requises avant réception complète | [Constats, preuves et priorités](docs/AUDIT_SOURCE_2026_10_27.md). Des tests verts ne couvrent pas tous les scénarios de panne ou de concurrence. |
| **Dépendances npm existantes** | Revue et mise à jour requises | Scan du 27 octobre : 10 entrées signalées (7 élevées, 3 modérées) ; dépendances indirectes et effet agrégé OpenClaw, exploitabilité à analyser. [Résultat et limites](docs/AUDIT_SOURCE_2026_10_27.md). |
| **Premier essai en Live USB** | Préqualification matérielle prévue | [Procédure autonome](docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md) ; aucun OpenClaw/Qwen/WebUI lancé par ce contrôle |
| **Montage et stockage `/data/IA/Openclaw/`** | Configuration commune Bash/Python/services, à qualifier sur le poste | EXT4 distinct du système, absence du disque refusée, UUID optionnel, liens interdits, stockage Podman dédié ; [procédure](docs/STOCKAGE_DATA.md) |
| **Fedora 45 / GNOME 51 / B580** | **À faire** | Installation et vérification de l’OS, pilote `xe`, Vulkan, affichage, veille sur le PC réel |
| **Qwen local et contexte 8K–32K** | Implémenté | Inférence courte dans `quick-check` ; débit réel, VRAM et contexte optimal **À mesurer** |
| **Open WebUI 0.12.3** | Implémenté/testé en simulation ou intégration partielle | Navigateur, boutons, fichiers et microphone **À faire** en réception réelle |
| **Sept rôles et projets multiples** | Contrats et tests automatisés ; scénarios pédagogiques multi-tours /20 et préférences approuvées | Réponses réelles, interactivité et qualité comparative Gemini/DeepSeek **À mesurer**, sans note automatique |
| **Cloud OpenRouter / DeepSeek V4.1 Flash 1017** | Instantané épinglé du 17 octobre ; filtres et budget testés en simulation | Appel OpenRouter réel, compatibilité `data_collection: deny`, `reasoning.effort`, coût et facturation **À faire** avec accord |
| **Parcours WebUI simplifié** | Implémenté, réception Open WebUI Fedora à effectuer | Six raccourcis, choix du projet et activité locale ; l’Atelier Projets partage le contexte de dossier/recherche/décisions. Voir [la prise en main](docs/fiches/03-discuter.md). |
| **Documents ODT** | Export éditable et import textuel implémentés | Source Markdown, téléchargements et provenance communs ; limites d’import [documentées](docs/fiches/06-fichiers-et-schemas.md). Réception dans le navigateur Fedora à effectuer. |
| **Sauvegarde / restauration** | Tests de restauration et SQLite fictif réussis | Restauration du vrai état de l’installation **À faire** |

Ces tests du dépôt **ne sont pas des essais sur le PC cible**. Le projet **n’a pas encore été réceptionné sur cette machine**.

## Versions déclarées pour la première installation

| Couche | Version/configuration dans le dépôt |
| --- | --- |
| Hôte | Fedora 45 Workstation, GNOME 51, Wayland ; Python système 3.15 |
| Runtime Python IA | Venv isolé Python 3.13 fourni par Fedora (compatibilité voix) |
| OpenClaw + plugin Parallel | `2026.10.4` |
| Ollama | `0.40.6` |
| Open WebUI | `v0.12.3-slim`, image résolue par digest à l’installation |
| Modèle local obligatoire | `qwen3.5:9b-q4_K_M` |
| Route cloud facultative | `deepseek/deepseek-v4.1-flash-1017` via OpenRouter |
| Budget cloud | 25 €/mois, activation et consentement explicites |
| Racine des données | `/data/IA/Openclaw/` sur le deuxième disque monté sous `/data` |

**Sources canoniques :** [versions](config/runtime_versions.yaml), [modèles](config/model_catalog.yaml), [plateforme](config/platform.yaml), [stockage](config/storage.json), [politique WebUI](config/webui_policy.yaml) et [politique cloud](config/core/cloud_policy.yaml). Le verrou des versions de production Python est décrit [ici](docs/PYTHON_RUNTIME_LOCK.md). **Une version déclarée n’est pas la preuve de sa présence sur le PC.**

**Nouvelle qualification pédagogique :** `clawfedora-pedagogy --plan` produit quatre scénarios de trois tours et une grille humaine clarté/profondeur/interactivité/exactitude (/5 chacun). La commande ne lance aucun modèle et ne dépense aucun crédit. Les préférences de style et un résumé d'acquis sont enregistrés seulement sur validation humaine depuis le tableau de bord ; elles n'équivalent pas à une mémoire automatique. Voir [le protocole](docs/EVALUATION_PEDAGOGIE.md).

## Parcours de qualification retenu

1. Préqualifier le matériel en [Live USB Fedora 45 / GNOME 51](docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md), puis examiner les corrections ouvertes. Pour l’atelier complet, installer Fedora stable et monter le disque secondaire sur `/data`.
2. Installer l’atelier et WebUI selon [la procédure simple](docs/INSTALLATION_SIMPLE_FEDORA45.md).
3. Exécuter **`./menu.sh --action quick-check`** : une réponse Qwen courte, vérification de la B580, des services, des interfaces et des projets.
4. Poser une question réelle dans Open WebUI et créer un projet de test. Si le résultat est satisfaisant, commencer à travailler.

**Fedora 45 :** au 27 octobre, la publication finale reste reportée avec une cible au 3 novembre ; vérifier la décision officielle avant de choisir l’ISO ([source et limites](docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md)). Une session Live ne valide pas la persistance ni les services de l’atelier installé.

Les benchmarks poussés, la série de cycles veille/reprise et les canaries (voix, streaming, vision) sont disponibles dans [les diagnostics avancés](docs/validation/README.md), **sans obligation au premier lancement**.

## Protections et limites du fonctionnement

- **Une génération à la fois** : les projets sont persistants et indépendants, mais l’exécution GPU est partagée ; aucune file FIFO durable n’est garantie.
- **Pas de déploiement autonome** : les agents produisent des propositions, scripts et documents ; l’utilisateur approuve et exécute les actions sensibles.
- **Cloud désactivé par défaut** ; pas de bascule locale vers DeepSeek cachée. Un accord cloud sur un projet ne garantit pas qu’un contenu privé soit publiable.
- Les outils `web_search` et `web_fetch` peuvent accéder à Internet même en mode local ; un [mode Web privé](docs/WEB_ACCESS_PRIVATE_MODE.md) est pilotable par `web-private --apply`, avec contrôle de la configuration enregistrée et du redémarrage du Gateway ; son absence d'egress réseau réel reste à vérifier.
- Le streaming SSE et la vision avancée sont disponibles sous **canary contrôlé**, pas activés ni qualifiés par défaut.
- Le verrou Python fixe les versions et hashes SHA-256 des artefacts de production ; le verrou npm SHA-512 est appliqué par `npm ci`. Les **21 dépendances de voix** sont également épinglées par versions et SHA-256 ; l'installation en environnement Fedora 45/Python 3.13 est vérifiée dans la CI. Les outils de construction setuptools/wheel sont désormais fixés par SHA-256 ; le runtime refuse les distributions sources et toute isolation PEP 517 non verrouillée. Les RPM Fedora et les extras de développement restent hors de ce verrou. Voir [les limites de reproductibilité](docs/PYTHON_RUNTIME_LOCK.md).
- Les sauvegardes locales ne sont **pas chiffrées** et résident initialement sur le même volume ; garder une copie externe protégée.
- Les fichiers proposés par les agents ne sont pas la preuve d’un déploiement Terraform/Ansible réussi.

## Corrections et travaux restant ouverts

L'[audit du 27 octobre](docs/AUDIT_SOURCE_2026_10_27.md) identifie les corrections prioritaires :
revue des avis npm, maintenance cohérente avec le runtime installé, verrouillage des sauvegardes/réparations,
reprise après timeout, ciblage des actions cloud, chargement fiable des règles privées
et récupération du journal budgétaire. Ces points sont **ouverts**, sans correctif fonctionnel
dans la présente révision documentaire. Le contrôle matériel Live peut être préparé en parallèle.

Les suivis antérieurs restent utiles :

| Suivi | Pourquoi c’est encore ouvert |
| --- | --- |
| [#122](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/122) | Qualification réelle Fedora 45 / B580 |
| [#123](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/123) | Réception WebUI, fournisseur OpenRouter, voix et restauration réelle |
| [#126](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/126) | Intégrité réseau et verrouillage transitif complet |
| [#124](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/124) | File persistante multi-projets facultative |

Les anciennes étapes d’octobre (OpenClaw 2026.10.3, Ollama 0.40.4, WebUI 0.12.1, migration depuis Fedora 44) appartiennent à [l’historique de 2026](docs/archives/2026/README.md), **pas aux versions de la nouvelle installation**.

[← Présentation](README.md) · [Documentation](docs/README.md) · [Historique des versions](CHANGELOG.md)
