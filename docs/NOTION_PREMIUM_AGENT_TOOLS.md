# Atelier Premium — outillage des agents et feuille de route

## Décision

OpsDesk inspire le standard de qualité, jamais un contenu à recopier. Les chartes universelles [Notion](NOTION_WIKI_DESIGN_SYSTEM.md), [GitHub](GITHUB_REPOSITORY_DESIGN_SYSTEM.md) et [Premium](EDITORIAL_PREMIUM_V2.md) restent les sources de référence. Les sept agents, trois modèles locaux et permissions sensibles restent inchangés.

| Rôle | Contribution |
| --- | --- |
| Chef | Périmètre, plan et critères de revue, inventaire |
| Recherche | Sources effectivement consultées et versions |
| Architecte | Navigation, structures, schémas et compilation de spécification |
| DevOps | Exactitude des commandes, code et preuves sur révision |
| Sécurité | Confidentialité, limites et partage |
| Rédacteur | Production native proposée, compilation, corrections |
| Audit | Inventaire, vérification indépendante, retour au producteur |

## Outils accessibles dans OpenClaw

- `clawfedora_notion_inventory` : pour les sept rôles. Scope relatif au workspace vers un dossier Notion importé contenant .source-provenance.json et les pages Markdown. Inventorie SHA, titres répétés, cinq intitulés de référence et emplacement de l'installation. Ne retourne pas les titres privés ou le contenu des pages ; retourner lire les lignes dans le snapshot si besoin. Les intitulés peuvent être adaptés : absence d'un titre exact est un signal, pas une preuve de défaut. Les répétitions de titres ne justifient aucune suppression. Le snapshot Markdown ne contient pas l'intégralité des données natives. Aucun accès réseau.
- `clawfedora_notion_studio_check` : architecte, rédacteur, auditeur. Utilise le vrai compilateur du studio via editorial_notion.parse/inspect, vérifie l'installation, les cinq espaces et le suivi unique. Entrée JSON au format studio dans content, jusqu'à 8000 octets. Résultat structurel uniquement ; un projet atypique peut justifier une adaptation. Pas de plan d'écriture, de token ou d'API.

Les outils sont enregistrés dans le manifeste natif, filtrés par rôle dans JavaScript et Python et déclarés dans la politique. Le statut d'outillage indique les outils autorisés en plus des validateurs disponibles. Les tests vérifient le refus hors rôle, chemins liés, conservation des octets et erreurs structurelles ; la CI ne démontre pas qu'un modèle sélectionne correctement son outil dans toutes les situations.

## Workflow

Importer la source Notion par le mécanisme existant, puis inventorier la version autorisée, lire les passages et proposer un plan de rationalisation. Le rédacteur prépare une spécification, l'architecte vérifie les espaces et l'auditeur la relit indépendamment. Utiliser le cycle éditorial borné déjà disponible et le studio opérateur avec approbation exacte. Aucune écriture, suppression ou validation d'autonomie par ces outils.

## Feuille de route et reprise

**Programme de consolidation v1.** ClawFedora accompagne l'apprentissage
InfraOps avec une interface native, OpenClaw et les trois modèles locaux
Qwen, Ornith et Gemma. Les choix actifs sont dans
[`model_routing.yaml`](../config/core/model_routing.yaml). Les preuves CI
s'attachent à un SHA. La recette matérielle reste soumise à la décision de
l'opérateur.

### C01 — Audit documentaire avancé dans Notion

| Lot | Livraison ou critère de clôture |
| --- | --- |
| 1. Outillage Premium | Inventaire Markdown et contrôle du studio par rôle livrés. [PR #298](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/298). |
| 2. Inventaire natif | Capture opérateur en lecture seule avec pagination, portée, empreintes et limites. [PR #299](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/299). |
| 3. Comparaison | [Comparateur hors ligne et rapport privé](NOTION_NATIVE_INVENTORY.md). Livré dans `main`. [PR #300](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/300). |
| 4. Doublons | [Rapport opérateur hors ligne](NOTION_DUPLICATES.md), signaux distincts et contextes protégés. Livré dans `main`. [PR #301](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/301). |
| 5. Liens et références | [Capture et audit des références](NOTION_REFERENCES.md). État structurel, expiration et observations opérateur. [PR #302](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/302). |
| 6. Sources de vérité | [Contrôle des références canoniques](NOTION_SOURCE_TRUTH.md) et comparaison des preuves des copies. [PR #303](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/303). |
| 7. Plans de rationalisation | [Plan de revue hors ligne](NOTION_RATIONALIZATION.md) avec preuves, impacts, approbations et contrôles de retour arrière. [PR #304](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/304). |
| 8. Intégration au worker | [Audits locaux du worker](NOTION_WORKER_AUDIT.md), autorisations par tâche et preuves vérifiées. [PR #305](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/305). |
| 9. Non-régression | [Audit avant/après](NOTION_NON_REGRESSION.md) sur une édition de texte autorisée, avec détection des écarts et protection des contenus. [PR #306](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/306). |
| 10. Recette | [Recette synthétique Atlas](validation/NOTION_ATLAS_ACCEPTANCE.md) et rapport JSON lié au SHA testé. [PR #307](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/307). |

**Référence avant le lot 10** — `main` à
[`9284a9a`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/9284a9acf379dc2c38339fa4c526c561fe756851), après fusion de la PR #306.
[CI](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45954034017) et
[CodeQL](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45954033762) sur ce SHA.

**Reprise** — C01 couvre la recette logicielle synthétique Atlas, livrée
sur [`a0136ca`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/a0136ca49d0a0986dc6b698a02c67e14db168329). Les
[preuves du SHA de `main`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45955352078)
sont rattachées à la CI. La réception Notion et la qualification Fedora
restent à planifier.

### C02 — Excellence documentaire GitHub

Le [premier lot](GITHUB_DOCUMENTARY_INVENTORY.md) est intégré à
[`main@9babca6`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/9babca6aa9f0cc79a7fb0eedefa52b90c4c16740).
Le [lot 2](GITHUB_DOCUMENTARY_LINKS.md) est intégré à
[`main@3dae57a`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/3dae57a1d87a74badaefe16b45b1339e7b97c2ba).
Le [lot 3](GITHUB_DOCUMENTARY_COHERENCE.md) est intégré à
[`main@e9023f8`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/e9023f84a96107e1aa60c181800d2938b6c48cd2).
Le [lot 4](GITHUB_DOCUMENTARY_CI.md) est intégré à
[`main@a8b3a54`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/a8b3a54400e31efd47040fc01a0eb0632037cc3c).
Le [lot 5](GITHUB_DOCUMENTARY_BOUNDARIES.md) est intégré à
[`main@8d54ff6`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/8d54ff6dcde9fa88315bebd4bdedf6840f1f65d8).
Le [lot 6](GITHUB_DOCUMENTARY_CORRECTIONS.md) est intégré à
[`main@898b0b5`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/898b0b5a0259aa30d6c31647a660d345c399021c).
Le [lot 7](GITHUB_DOCUMENTARY_VERIFICATION.md) est intégré à
[`main@1de3c86`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/1de3c86636bcf405ae585da55541da7d6eff9e80).
La [recette synthétique Atlas](validation/GITHUB_DOCUMENTARY_ACCEPTANCE.md)
clôt le périmètre logiciel C02. La CI vérifie les sept lots et
identifie le commit testé dans le rapport. La recette est intégrée à
[`main@ceef459`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/ceef459b9d504ed5fc540efe3c33620d24844dd2).

### C03 — Orchestration des agents

Le [lot 1](fiches/04-atelier-projets.md) rend le choix de chaque rôle
visible et modifiable avant l'approbation. Le chef propose les rôles
utiles à la mission et justifie leur contribution. L'opérateur peut
retirer une tâche et corriger les dépendances avant l'assignation.
Après intégration, reprendre la transmission des livrables et de leur
provenance entre les tâches approuvées.


### Programme restant

| Chantier | Critère de clôture |
| --- | --- |
| C03 — Orchestration | Sélectionner les rôles utiles, transmettre les preuves et tester la reprise et les corrections bornées avec audit indépendant. |
| C04 — Continuité | Reprendre une mission à partir d'objectifs, décisions et preuves datés et cloisonnés par projet. |
| C05 — Navigateur | Tester l'observation dans une session isolée, puis des interactions bornées et approuvées. |
| C06 — Bureau Fedora | Préparer et simuler les contrats de consentement et de contrôle Wayland. Qualification sur la session cible en C12. |
| C07 — Interface | Consolider le pilotage des missions, livrables et validations dans les espaces existants. |
| C08 — Résilience et sécurité | Couvrir les erreurs, interruptions, rejouements, données non fiables et conflits dans chaque lot. |
| C09 — Documentation | Réconcilier l'état actif, le code, les preuves et les guides historiques. |
| C10 — Recette logicielle | Exécuter la [recette globale](RECETTE_GLOBALE.md) avec des données synthétiques avant installation. |
| C11 — Installation | Préparer et installer Fedora et ClawFedora après décision explicite de l'opérateur. |
| C12 — Qualification réelle | Mesurer le matériel et vérifier les sept agents, les outils, les intégrations et la restauration sur le poste cible. |

**Blocages et limites** — C11 et C12 sont reportés. Les limites de lecture du
wiki figurent dans le [guide d'inventaire](NOTION_NATIVE_INVENTORY.md).
Les tests du lot 3 utilisent des données synthétiques. Les opérations
sensibles et les fusions passent par l'opérateur.
