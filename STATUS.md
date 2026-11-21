# État du projet — Atelier IA hybride Fedora

**Version 0.2.0 du 3 novembre 2026** ([notes de version](CHANGELOG.md)). **Cycle d'optimisation FinOps #196–#201 intégré au dépôt.** Les PR Notion #213 (bloc simple), #215 (lot multi-blocs) et #216 (panneau local) ont été fusionnées le 21 novembre 2026. La prise en charge conservatrice des segments enrichis est proposée séparément dans une nouvelle PR. Vérifier la CI et la réception du SHA effectivement déployé. L’état ci-dessous distingue ce qui est dans le code, ce que GitHub Actions vérifie et ce qui dépend encore du PC et des fournisseurs réels. **Une CI verte n’est pas une preuve d’exploitation sur Fedora.**

**Évolution en cours de qualification :** routage cloud par niveau de tâche
approuvé (`simple`, `complex`, `critical`), protocole de mesure
Qwen/DeepSeek/Sol et validation Kubernetes hors ligne dans le laboratoire
isolé. Le modèle Qwen n'est **pas supprimé** ; le classement réel
des trois modèles et la réception Fedora restent à faire.
Voir [stratégie cloud-first](docs/CLOUD_FIRST_QUALIFICATION.md).

## Résumé vérifiable

| Dimension | Statut | Preuve ou limite |
| --- | --- | --- |
| **Code, règles et installation** | Contrats automatisés réussis ; défauts de l’audit corrigés (A01 à A12) | Tests Python 3.12/3.13, ShellCheck, conteneurs Fedora 44/45, OpenClaw natif ; [audit et corrections](docs/AUDIT_SOURCE_2026_10_27.md) |
| **Référence historique de CI après fusion de la PR #165** | Succès | [Commit `2cab2b3`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/2cab2b3860d08b31a6f95217c5fc2116829505e4), vérifié le 3 novembre : [dix jobs réussis](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/41573194535), 1 205 tests dans le job quality, couverture 86 %. Instantané daté, antérieur à la release 0.2.0 : consulter la CI du dernier commit avant de s’y fier. |
| **Contrôle local du 9 novembre 2026** | Vérifié, portée locale | `pytest -q` : 1 215 réussis, 4 ignorés ; `ruff check src tests scripts/validation plugins`, `mypy src` (78 fichiers), `shellcheck menu.sh scripts/linux/*.sh scripts/linux/lib/*.sh` et `clawfedora validate` sans erreur. Exécutés dans un conteneur Linux (Python 3.13), **pas sur Fedora 45 ni sur le PC cible**. |
| **Analyse statique** | Succès sur cette référence | [CodeQL après fusion](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/41573194538) ; chaque nouvelle PR repasse ce contrôle |
| **Audit du 27 octobre** | 12 défauts sur 13 corrigés, avec tests de régression | A01–A12 corrigés par les PR #157 à #163. Reste A13 (installation lancée depuis une session Live), sans effet sur une installation Fedora normale. Des tests verts ne couvrent pas tous les scénarios de panne réels. |
| **Dépendances npm** | Revues le 2 novembre ; 1 alerte élevée résiduelle | OpenClaw 2026.10.5 et 3 correctifs imposés : 6 alertes élevées → 1 (`undici` embarqué dans `npm`, sans correctif publié). [Analyse et résidus](docs/audits/2026-11-02/README.md). Audit hebdomadaire automatique des verrous npm et Python, avec exceptions revues et datées ; Dependabot propose les mises à jour. |
| **Réception sur le PC** | **À faire** | Suivre la [liste de contrôle de réception](docs/RECEPTION_ETAPE3.md) ; le [Live USB](docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md) reste facultatif |
| **Montage et stockage `/data/IA/Openclaw/`** | Configuration commune Bash/Python/services, à qualifier sur le poste | EXT4 distinct du système, absence du disque refusée, UUID optionnel, liens interdits, stockage Podman dédié ; [procédure](docs/STOCKAGE_DATA.md) |
| **Fedora 45 / GNOME 51 / B580** | **À faire** | Installation, pilote `xe`, Vulkan, affichage et veille sur le PC réel. Node.js : le paquet `nodejs24` (24.18.0) est installé, car le `nodejs` par défaut de Fedora 45 (Node 22) est refusé par OpenClaw (vérifié en CI dans le conteneur Fedora 45). |
| **Qwen local et contexte 8K–32K** | Implémenté | Inférence courte dans `quick-check` ; débit réel, VRAM et contexte optimal **À mesurer** |
| **Open WebUI 0.12.3** | Implémenté et testé en simulation ou intégration partielle | Navigateur, boutons, fichiers et microphone **À faire** en réception réelle |
| **Sept rôles et projets multiples** | Contrats et tests automatisés ; livrables scellés par les audits | Réponses réelles et qualité comparée Qwen/DeepSeek/Sol **À mesurer**, sans note automatique |
| **Cloud OpenRouter / DeepSeek et Sol** | Routage cloud par rôle et étape approuvée, choix manuel conservé ; qualification réelle à faire | `auto` par défaut : `standard` (V4.1 Flash 1017) en routine et `expert` (GPT-6.2 Sol, [fiche cloud](docs/fiches/12-cloud.md)). Appel réel, fournisseur effectivement retenu, coût et facturation **À faire** avec accord. |
| **Maintenance** | Désinstallation, purge, sauvegarde et réparation protégées | Arrêt vérifié avant suppression, purge sans perte partielle, maintenance refusée pendant une génération. Restauration du vrai état de l’installation **À faire**. |
| **Parcours WebUI simplifié** | Implémenté ; réception Open WebUI Fedora à effectuer | Six raccourcis, choix du projet et activité locale ; voir [la prise en main](docs/fiches/03-discuter.md) |
| **Documents ODT** | Export éditable et import textuel implémentés | Limites d’import [documentées](docs/fiches/06-fichiers-et-schemas.md) ; réception dans le navigateur Fedora à effectuer |
| **GitHub / Notion** | Import en lecture seule ; GitHub sous approbation ; écriture Notion sous approbation (bloc simple et lot multi-blocs) fusionnée ; panneau de revue local fusionné #216 ; édition par segment enrichi proposée en PR distincte | [Panneau Notion](docs/NOTION_DASHBOARD.md) ; [édits multi-blocs](docs/NOTION_MULTI_BLOCK.md) ; [mode texte enrichi](docs/NOTION_RICH_TEXT.md) ; [recette complète](docs/validation/NOTION_GITHUB_ACCEPTANCE.md). Réception sur Fedora, compte Notion et navigateur réel **à faire**. |

Ces tests du dépôt **ne sont pas des essais sur le PC cible**. Le projet **n’a pas encore été réceptionné sur cette machine**.

## Versions déclarées pour la première installation

| Couche | Version/configuration dans le dépôt |
| --- | --- |
| Hôte | Fedora 45 Workstation, GNOME 51, Wayland ; Python système 3.15 |
| Runtime Python IA | Venv isolé Python 3.13 fourni par Fedora (compatibilité voix) |
| OpenClaw + plugin Parallel | `2026.10.5` (+ 3 correctifs npm imposés) |
| Node.js | Fedora `nodejs24` (24.18.0) ; le `nodejs` par défaut (22) est refusé par OpenClaw |
| Ollama | `0.40.6` |
| Open WebUI | `v0.12.3-slim`, image résolue par digest à l’installation |
| Modèle local obligatoire | `qwen3.5:9b-q4_K_M` |
| Route cloud facultative | `deepseek/deepseek-v4.1-flash-1017` par défaut ; `openai/gpt-6.2-sol` en expertise selon le rôle et l'étape, ou sur choix manuel, via OpenRouter |
| Contexte et cache | Historique JSON compact, extraits vérifiés SHA-256 et ratio de cache documenté ; gain réel à mesurer. |
| Budget cloud | 35 €/mois, dont enveloppes de 15 € DeepSeek / 10 € Sol et 10 € non routables ; activation et consentement explicites |
| Racine des données | `/data/IA/Openclaw/` sur le deuxième disque monté sous `/data` |

**Sources canoniques :** [versions](config/runtime_versions.yaml), [modèles](config/model_catalog.yaml), [plateforme](config/platform.yaml), [stockage](config/storage.json), [politique WebUI](config/webui_policy.yaml) et [politique cloud](config/core/cloud_policy.yaml). Le verrou des versions de production Python est décrit [ici](docs/PYTHON_RUNTIME_LOCK.md). **Une version déclarée n’est pas la preuve de sa présence sur le PC.**

**Qualification pédagogique :** `clawfedora-pedagogy --plan` produit quatre scénarios de trois tours et une grille humaine clarté/profondeur/interactivité/exactitude (/5 chacun). La commande ne lance aucun modèle et ne dépense aucun crédit. Les préférences de style et un résumé d’acquis ne sont enregistrés qu’après validation humaine depuis le tableau de bord ; ce n’est pas une mémoire automatique. Voir [le protocole](docs/EVALUATION_PEDAGOGIE.md).

Audit de cohérence préinstallation : [constats et corrections du 20 novembre 2026](docs/audits/2026-11-20/README.md). Il ne remplace pas la réception réelle sur Fedora.

## Cycle FinOps et qualification

| Lot | PR | Résultat intégré |
| --- | --- | --- |
| 1 | [#196](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/196) | Mesure des tokens et du cache |
| 2 | [#197](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/197) | Deux modèles cloud et plafond global |
| 3 | [#198](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/198) | Routage et enveloppes par modèle |
| 4 | [#199](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/199) | Contexte compact et provenance |
| 5 | [#200](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/200) | Prompts et guide d'outils dédupliqués |
| 6 | [#201](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/201) | Prévalidation des audits et intégrité |

La [recette finale FinOps](docs/validation/FINOPS.md) définit les vérifications hors ligne déjà automatisées et les mesures réelles à recueillir. La réception Fedora, la qualité des modèles, les prix facturés et les gains de cache restent non démontrés.

## Parcours de qualification retenu

1. Installer Fedora 45 Workstation stable et monter le deuxième disque sur `/data`.
2. Installer l’atelier et WebUI selon [la procédure simple](docs/INSTALLATION_SIMPLE_FEDORA45.md).
3. Exécuter **`./menu.sh --action quick-check`** : une réponse Qwen courte, vérification de la B580, des services, des interfaces et des projets.
4. Dérouler la [liste de contrôle de réception](docs/RECEPTION_ETAPE3.md) : chat local, premier projet jusqu’à la livraison, sauvegarde, redémarrage et, si souhaité, cloud borné.

**Fedora 45 :** d’après la presse spécialisée, la version finale a été déclarée « GO » le 29 octobre (RC 1.4), pour une sortie le 3 novembre ([Phoronix](https://phoronix.com/news/Fedora-45-Ships-Next-Week)). Vérifier l’annonce officielle sur [fedoraproject.org](https://fedoraproject.org/) avant de choisir l’ISO.

Les benchmarks poussés, les cycles de veille et reprise et les canaries (voix, streaming, vision) sont dans [les diagnostics avancés](docs/validation/README.md), **sans obligation au premier lancement**.

## Protections et limites du fonctionnement

- **Une génération à la fois** : les projets sont persistants et indépendants, mais l’exécution GPU est partagée ; aucune file FIFO durable n’est garantie. Un traitement interrompu (délai dépassé, redémarrage) s’affiche en échec ou « interrompu », jamais « en cours » indéfiniment.
- **Pas de déploiement autonome** : les agents produisent des propositions, scripts et documents ; l’utilisateur approuve et exécute les actions sensibles. Un livrable modifié après les audits ne peut pas être livré sans reprise approuvée.
- **Cloud désactivé par défaut** ; aucune bascule cachée du local vers le cloud, ni escalade sur panne ou refus ; le choix interne au cloud suit les règles de rôle et d'étape. Un accord cloud vise un seul projet et ne garantit pas qu’un contenu privé soit publiable. Une liste de termes sensibles illisible refuse le cloud.
- Les outils `web_search` et `web_fetch` peuvent accéder à Internet même en mode local ; un [mode Web privé](docs/WEB_ACCESS_PRIVATE_MODE.md) est pilotable par `web-private --apply`, avec contrôle de la configuration enregistrée et du redémarrage du Gateway. L’absence réelle de trafic réseau reste à vérifier.
- Le streaming SSE et la vision avancée sont disponibles sous **canary contrôlé**, ni activés ni qualifiés par défaut.
- Le verrou Python fixe les versions et les hashes SHA-256 des artefacts de production ; le verrou npm SHA-512 est appliqué par `npm ci`, avec les correctifs imposés contrôlés. Les **21 dépendances de voix** sont aussi épinglées par versions et SHA-256 ; leur installation sous Fedora 45/Python 3.13 est vérifiée en CI. L'outil de construction setuptools (84.2.1, le paquet `wheel` n'étant plus nécessaire) est fixé par SHA-256 ; le runtime refuse les distributions sources et toute isolation PEP 517 non verrouillée. Les RPM Fedora et les extras de développement restent hors de ce verrou. Voir [les limites de reproductibilité](docs/PYTHON_RUNTIME_LOCK.md).
- Les sauvegardes locales ne sont **pas chiffrées** et résident sur le même volume ; garder une copie externe protégée.
- Les fichiers proposés par les agents ne prouvent pas qu’un déploiement Terraform/Ansible a réussi.

## Travaux restant ouverts

| Suivi | Pourquoi c’est encore ouvert |
| --- | --- |
| Réception sur le PC | Toutes les mesures réelles : [liste de contrôle](docs/RECEPTION_ETAPE3.md) |
| A13 | L’installateur ne refuse pas explicitement une session Live ; sans effet sur une installation normale |
| [#122](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/122) | Qualification réelle Fedora 45 / B580 |
| [#123](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/123) | Réception WebUI, fournisseur OpenRouter, voix et restauration réelle |
| [#126](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/126) | Intégrité réseau et verrouillage transitif complet |
| [#124](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/issues/124) | File persistante multi-projets facultative |

Les anciennes étapes d’octobre (OpenClaw 2026.10.3, Ollama 0.40.4, WebUI 0.12.1, migration depuis Fedora 44) appartiennent à [l’historique de 2026](docs/archives/2026/README.md), **pas aux versions de la nouvelle installation**.

[← Présentation](README.md) · [Documentation](docs/README.md) · [Historique des versions](CHANGELOG.md)
