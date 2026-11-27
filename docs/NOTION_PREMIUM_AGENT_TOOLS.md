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
| 4. Doublons | [Rapport opérateur hors ligne](NOTION_DUPLICATES.md), signaux distincts et contextes protégés. Revue et CI avant fusion. |
| 5. Liens et références | Contrôler les destinations et distinguer référence cassée, accès restreint, lien temporaire et destination non vérifiable. |
| 6. Sources de vérité | Localiser les références et relever les copies divergentes selon le projet. |
| 7. Plans de rationalisation | Relier chaque action proposée à une preuve, un emplacement, un impact, une approbation et un contrôle de retour arrière. |
| 8. Intégration au worker | Réutiliser les rôles, les écritures contrôlées, les approbations et l'audit indépendant. |
| 9. Non-régression | Comparer l'état relu après modification et vérifier les changements attendus, les contenus protégés et la navigation. |
| 10. Recette | Vérifier la couverture et les limites sur Atlas ou un wiki synthétique équivalent. Documenter les anomalies, preuves et verdicts. |

**Référence avant le lot 4** — `main` à
[`76334c5`](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/commit/76334c5c46df3d8e10cc2a508336bc4043cfbb67), après la fusion de la PR #300.
[CI](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45944184337) et
[CodeQL](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45944184374) sur ce SHA.

**Reprise après le lot 4** — Vérifier la fusion et la CI du SHA de `main`.
Ouvrir le lot 5 avec une recette synthétique des liens de pages et de blocs.
Distinguer une destination cassée d'un refus d'accès, d'une URL temporaire
expirée ou d'une destination dont l'état demeure non vérifiable.


### Programme restant

| Chantier | Critère de clôture |
| --- | --- |
| C02 — Audit GitHub | Vérifier la documentation et les preuves d'un dépôt à une révision identifiée. Préparer les corrections sous revue. |
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
