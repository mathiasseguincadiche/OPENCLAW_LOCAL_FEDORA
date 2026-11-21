# Réception intégrée — Notion, GitHub, agents, graphisme et Fedora

[← État](../../STATUS.md) · [Notion contrôlé](../NOTION_CONTROLLED_WRITES.md) · [Notion multi-blocs](../NOTION_MULTI_BLOCK.md) · [Panneau Notion](../NOTION_DASHBOARD.md) · [Mode texte enrichi](../NOTION_RICH_TEXT.md) · [Tableaux et images](../NOTION_TABLES_IMAGES.md) · [GitHub](../GITHUB_CHAT_DASHBOARD.md) · [Réception Fedora](../RECEPTION_ETAPE3.md)

Pour préparer les captures sur le poste cible et vérifier leurs preuves,
suivre la [procédure de réception visuelle native](VISUAL_RECEPTION_NATIVE.md).
L'outillage capture et collecte les données ; il ne remplace pas une revue
humaine de chaque page réelle.

La [refonte de l'interface locale](../WORKBENCH_UI_DESIGN.md) doit être
contrôlée comme un vrai produit : navigation entre les trois espaces,
onglets utilisables au clavier, formulaire de plan, approbation et erreurs,
mode clair/sombre, mobile et absence de débordement. Une capture ne
remplace pas le test interactif sur Fedora.

## Règle d'évaluation

Ce protocole **ne donne aucun verdict d'exploitation sans réalisation effective**.
Conserver : date, SHA du code, machine, commandes, sorties expurgées, page/dépôt
cibles, approbation, captures réelles et limites. Une CI verte ne démontre ni
l'installation sur le PC ni le rendu dans Notion ou GitHub.

Le projet témoin peut être un nouveau projet **fictif** et privé. Ne pas écrire
dans les treize exercices personnels OpsDesk ni dans la base de progression.

## Périmètres et preuve attendue

| Étape | Action de réception | Preuve acceptable | État avant exécution sur Fedora |
| --- | --- | --- | --- |
| 1. Notion | Prévisualiser une correction d'un bloc texte de page de test, puis appliquer sous accord | Diff, SHA, ID exact, lecture après PATCH, capture avant/après | Non exécutée sur Fedora |
| 2. GitHub | Créer un dépôt privé de test sous approbation ; auditer ruleset, Actions, README et PR brouillon | URL réelle, paramètres relus, SHA de base, PR, contrôles réels | Non exécutée sur Fedora |
| 3. Agents | Donner un même besoin InfraOps aux sept rôles : architecture, rédaction Notion, README GitHub, DevOps, recherche, sécurité, audit | Livrables distincts, décisions, revue indépendante, refus et correction des incohérences | Non qualifiée sur modèle réel |
| 4. Rendu Notion | Inspecter accueil, fiche de cours, installation, pages liées, sommaire et vue mobile | Captures natives, liens testés, sous-pages/bases conservées | Non vérifié graphiquement par la CI |
| 4. Rendu GitHub | Inspecter README en clair, sombre et mobile, schéma présentation/technique et légendes | Trois captures navigateur réelles datées + manifeste d'intégrité | Non vérifié graphiquement par la CI |
| 5. Fedora | Installer, effectuer `quick-check`, un projet complet, sauvegarde, restauration, redémarrage | Journaux expurgés, versions, intégrité des données, refus contrôlés | À réaliser sur PC cible |

## Ordre opératoire recommandé

1. Installer le projet sur Fedora 45, confirmer le montage `/data` et
   exécuter `./menu.sh --action quick-check` et les contrôles de
   `docs/RECEPTION_ETAPE3.md` **avant toute publication externe**.
2. Lancer un projet d'essai avec les sept agents. Documenter **qui fait quoi** :
   chef (cadre et approbations), architecte (structure), expert (sources),
   rédacteur (page/README), DevOps (commandes et dépôt), sécurité (secrets
   et accès), auditeur (revue indépendante).
3. Produire une petite modification d'un **bloc simple** sur une page Notion
   de test ; voir `docs/NOTION_CONTROLLED_WRITES.md`. Refuser les demandes
   d'effacement de sous-pages, de suivi fictif, de disparition de la section
   d'installation et d'écriture depuis le modèle sans confirmation humaine.
4. Préparer la structure et le dépôt privé de test avec
   `clawfedora-github-scaffold`, `clawfedora-github-remote`,
   `clawfedora-github-audit` puis `clawfedora-github-pr` ou le panneau
   `/github.html`. Vérifier la visibilité privée et la PR brouillon
   sans la fusionner automatiquement.
5. Contrôler les rendus natifs. Comparer les vrais diagrammes SVG aux sources
   `.drawio`, inspecter GitHub sur mobile et Notion sur desktop/mobile. Ne
   pas transformer un manifeste SHA-256 en note de qualité visuelle.
6. Exécuter les essais de sauvegarde/restauration et les vérifications
   matérielles dans le laboratoire personnel, puis noter seulement
   les résultats effectivement observés.

## Critères de sortie

- **STRUCTURE_VERIFIEE :** sources, hiérarchie Notion, documentation GitHub,
  sections d'installation et liens contrôlés.
- **RENDU_VISUEL_VERIFIE :** pages réellement ouvertes et relues en bureau,
  mobile, clair/sombre lorsque pertinent ; captures datées.
- **TECHNIQUE_EXECUTEE :** commandes et restaurations exécutées sur le poste ou
  une VM désignée, sorties expurgées, tests et retour arrière justifiés.
- **AGENTS_QUALIFIES :** scénarios de rôles réellement joués avec les modèles
  retenus et appréciation humaine de la précision et de l'autonomie.

Les quatre verdicts sont indépendants. Une CI peut confirmer des contrôles
de code mais ne peut pas attribuer tous ces verdicts. Après les essais,
mettre à jour le journal de réception avec **PASS / FAIL / NOT_EVALUATED**
et les preuves exactes, sans anticiper les résultats.
