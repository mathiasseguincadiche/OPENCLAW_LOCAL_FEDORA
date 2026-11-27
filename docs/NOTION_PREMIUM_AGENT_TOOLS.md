# Atelier Premium — outillage des sept agents, lot 1

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

## Suite du programme

1. Inventaire natif récursif complet du wiki autorisé (blocs, bases, relations, vues, médias, permissions accessibles), conservation et limites explicites.
2. Plans d'évolution ciblés et relecture après application : dédoublonnage sémantique, archives, modification structurelle et cohérence GitHub/Notion ; validation par opérateur.
3. Intégration du studio et des plans dans le worker et l'interface, contrôle de portée et preuves, revue multi-rôles.
4. Browser Use via session Playwright isolée : observation d'abord, actions bornées et consentement.
5. Computer Use Fedora Wayland : étude de compatibilité, session XDG Desktop Portal/PipeWire/libei à consentement révocable, observation Qwen Vision, actions contrôlées sans accès root. Pas de saisie de secret, pas de contrôle du bureau personnel permanent.
6. Recette synthétique Atlas puis essais natifs Fedora. Aucun changement sur OpsDesk par ce chantier.

**État : premier lot local de préparation, intégration distante et contrôle PC non livrés.**


[Inventaire natif récursif en lecture seule — lot 2](NOTION_NATIVE_INVENTORY.md).
