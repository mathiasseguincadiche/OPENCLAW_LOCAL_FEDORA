# Charte GitHub premium — Référentiel universel pour l'atelier InfraOps

Le [standard transversal d’excellence éditoriale](EXCELLENCE_EDITORIALE.md) fixe la grille et les blocages communs ; les règles ci-dessous restent spécifiques au support.

[← Source GitHub / Notion](INTEGRATION_GITHUB_NOTION.md) · [Wiki Notion](NOTION_WIKI_DESIGN_SYSTEM.md) · [Sept agents](fiches/07-roles-et-outils.md)

## Deux sources complémentaires

**GitHub est la vitrine technique et la source versionnée** : code, scripts, IaC, contrats, architectures, décisions, CI/CD, exploitation, preuve datée, sécurité et historique. **Notion est le wiki de formation** : cours longs, progression, notes de séance, exercices complets et difficultés personnelles. Ne pas copier les notes privées de l'apprenant dans un dépôt public ni déduire d'une CI que l'exercice est maîtrisé.

Le même standard GitHub s'applique à un projet de service, un laboratoire de réseau, une architecture Terraform ou un outil d'exploitation, **sans imposer une arborescence unique ou une stack fixe**.

## 1. README comme porte d'entrée

Le README doit permettre de trouver trois choses en moins de dix secondes :
**de quoi parle le projet, où commencer, et que peut-on réellement vérifier ?**

Ordre conseillé :
1. Illustration éditoriale ou logo natif, alt et contraste contrôlés.
2. Nom, pitch métier et responsabilités du projet.
3. Navigation rapide : aperçu, installation, architecture, état et documentation.
4. Capture réelle datée, si application graphique, ou schéma de présentation sourcé.
5. Démarrage avec prérequis, inventaire, commandes, validation, arrêt/rollback.
6. Architecture synthétique et lien vers la vue technique distincte.
7. Réalisations, statut honnête, preuves accessibles, limites connues.
8. Index documentaire et liens de contribution, sécurité, provenance, licence.

**L'identité graphique est au service du lecteur** : palette cohérente, image originale, typographie GitHub native, espace, peu de badges, contraste clair/sombre et lecture mobile. Une capture simulée n'est pas une capture d'application. Une bannière purement éditoriale n'est pas un schéma d'architecture ni une preuve de déploiement.

## 2. Organisation et niveaux de lecture

| Lecteur | Première porte d'entrée | Approfondissement |
| --- | --- | --- |
| Découverte ou recrutement | README, aperçu, rôle personnel, état réel | Architecture et démonstrations |
| Débutant et apprenant | Installation, exemple puis vérification | Wiki Notion et parcours adapté |
| Développeur ou contributeur | Contribution, environnement, tests, PR | Contrats, architecture, ADR |
| Ingénieur expérimenté | Diagrammes, code, flux, compromis | Tests, preuves, sécurité, exploitation |
| Mainteneur | STATUS/ROADMAP, runbooks, risques | Versions, changelog, rollback |

Éviter les doublons entre README, guide technique, preuve et wiki personnel. Un lien peut être plus utile qu'une copie intégrale.

## 3. Sept gabarits réutilisables

- [README projet](../templates/github/readme-projet.md)
- [Architecture et ADR](../templates/github/architecture-adr.md)
- [Guide et runbook d'exploitation](../templates/github/runbook.md)
- [Dossier de preuves](../templates/github/preuve.md)
- [Pull request](../templates/github/pull-request.md)
- [Issue / anomalie](../templates/github/issue.md)
- [Notes de version](../templates/github/release-notes.md)

Chaque modèle contient des rubriques obligatoires mais s'adapte à la fonction de sa page ; ne pas fabriquer sept pages si deux suffisent. Un modèle est un **support de rédaction**, jamais une preuve.

## 4. Exigences documentaires et techniques

**Procédure :** vérifier notamment les titres répétés, les clôtures des blocs de code et les étapes réellement utiles ; ce sont des signaux de relecture, pas un verdict. Expliquer le pourquoi, la cible et le niveau de droits, les prérequis, l'inventaire des outils existants, l'installation conditionnelle, les commandes annotées, le contrôle attendu, les erreurs, les tests de refus pertinents et le rollback. Ne jamais supprimer « installation des outils ».

**Architecture :** schéma de présentation et schéma technique distincts ; sources `.drawio` + exports `.svg` pour les diagrammes, légendes, ports, flux, responsabilités et limites. Exporter le SVG depuis la source, contrôler son affichage sur GitHub et mobile ; le simple XML valide ne démontre pas sa lisibilité. Utiliser des vues distinctes : 3 à 5 blocs pour présenter, détails seulement dans la vue technique. Contrôler ancrages, chevauchements, flux lisibles et légendes, sans déduire la réalité technique du dessin.

**Preuve :** date, cible, commit/digest, méthode, attendu, observé, statut et limites. Différencier existence, analyse statique, test CI, déploiement sur machine, santé métier, récupération après incident et autonomie individuelle.

**Sécurité :** permissions minimales, pas de secrets dans Git, dépendances contrôlées, procédures de signalement privées quand disponibles, pas de badges « secure » non fondés.

## 5. Auditeur local GitHub — première capacité concrète

`clawfedora-github-audit` examine un dossier **local**, sans requête réseau,
exécution de code, lecture de secrets ou écriture sur GitHub. Il signale la
présence des composants documentaires, les chemins locaux cassés, le XML
des diagrammes SVG et les paires Draw.io/SVG.

```bash
# Sur une copie locale du dépôt ou un instantané importé volontairement :
clawfedora-github-audit --path /chemin/vers/le/depot

# Enregistrer les constats sans rien changer au dépôt examiné :
clawfedora-github-audit --path /chemin/vers/le/depot > audit-github.json
```

Si l'on importe GitHub avec `clawfedora-sources --github propriétaire/depot
--commit <sha-complet> --apply`, fournir le **chemin réel** du snapshot
`intake/GitHub-...-<sha12>` à cette commande. L'importation exclut notamment
les fichiers binaires : une capture PNG introuvable dans un **snapshot
partiel** n'est pas automatiquement un lien cassé. L'audit renvoie alors
`NOT_CHECKED`, et non une preuve d'absence.

Le rapport utilise `FOUND`, `NOT_FOUND`, `NOT_CHECKED` et
`READ_ONLY_DOCUMENTARY_INVENTORY_NOT_A_RUNTIME_PROOF`. Il n'attribue
**aucun score professionnel, état de pipeline vert, résultat de déploiement
ou niveau de maîtrise**.

Limites connues : pas de navigation GitHub native, pas de rendu navigateur,
pas de validation des ancres, pas de scan réel des vulnérabilités, pas
d'exécution de tests sur VM, pas de PR automatique. Le périmètre est
strictement documentaire et structurel.

## 6. Répartir la responsabilité sans augmenter artificiellement les agents

- **Chef :** définit l'objectif et les validations humaines ; décide s'il faut un audit simple ou plusieurs spécialités.
- **Architecte :** conçoit l'arborescence, sépare les schémas et justifie les décisions.
- **Rédacteur :** reformule et met en page README, guides et procédures sans cacher les limites.
- **DevOps :** examine les scripts, les tests et la chaîne InfraOps ; propose des diff/PR vérifiables.
- **Sécurité :** contrôle exposition, permissions, secrets et dépendances sans promettre de conformité non testée.
- **Recherche :** confirme les options, versions et règles GitHub actuelles.
- **Auditeur :** confronte le rapport statique aux fichiers, preuves et rendus réellement consultés.

Des rôles GitHub dédiés ne deviennent utiles qu'après démonstration d'un besoin
d'orchestration supplémentaire ; ne pas dupliquer les compétences existantes.

## 7. Workflow d'amélioration du dépôt

1. Fixer le dépôt et son SHA. Lire README, contrat, STATUS et architecture.
2. Contrôler les liens, schémas, sécurité, code et CI existants ; noter les manques et les limites.
3. Proposer **deux options graphiques** quand une refonte majeure est demandée, sans reproduire un gabarit identique pour tous les projets.
4. Présenter les changements et les conséquences, surtout pour l'arborescence, la sécurité et les exercices.
5. Appliquer seulement les modifications validées via branche/PR ; préserver code, tests, liens et preuves.
6. Exécuter les tests disponibles sur la révision exacte ; distinguer CI du socle et exercice personnel.
7. Effectuer une recette GitHub **native** (clair/sombre, ordinateur/mobile, liens, images) ; ne pas revendiquer cette recette si seul le code a été contrôlé.
8. Demander la revue avant fusion, conserver les problèmes ouverts et mettre à jour STATUS uniquement sur preuve.

Pour une première publication, consulter aussi [la création et la protection des dépôts GitHub](GITHUB_REMOTE_SETUP.md) ; la visibilité et les règles restent sous approbation.

## 8. Création de dépôt et publication guidée

Le [protocole de gouvernance et publication GitHub](GITHUB_PUBLICATION_WORKFLOW.md)
précise les responsabilités et trois commandes : `clawfedora-github-scaffold`
(structure locale), `clawfedora-github-audit` (inventaire statique) et
`clawfedora-github-pr` (préparation hors ligne, puis création
**explicite** d'une branche et d'une PR en brouillon dans un dépôt existant).
La création d'un nouveau dépôt distant, la fusion et les paramètres GitHub
restent des opérations humaines distinctes.

## 9. Cas d'usage vérifié de la démarche

Le dépôt [OpsDesk](https://github.com/mathiasseguincadiche/OpsDesk)
fournit un exemple de charte appliquée ; ce n'est **pas** un modèle fixe que
les agents doivent recopier partout. Sa version et ses preuves vivent dans
son propre `STATUS.md`.

**Étape future, non implémentée :** naviguer sur GitHub depuis chaque message
du modèle, vérifier la recette graphique dans un navigateur, générer et publier
des PR sans intervention. Ces opérations nécessitent un périmètre de droits,
un mécanisme d'approbation et des tests distincts.