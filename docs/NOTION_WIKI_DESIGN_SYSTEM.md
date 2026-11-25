# Charte universelle — Wikis techniques Notion

[← Sources GitHub et Notion](INTEGRATION_GITHUB_NOTION.md) · [Cas OpsDesk](CAS_USAGE_INFRAOPS_OPSDESK.md) · [Rôles](fiches/07-roles-et-outils.md)

Pour la présentation et les contrôles de la source technique,
consulter aussi la [charte universelle GitHub](GITHUB_REPOSITORY_DESIGN_SYSTEM.md).
Elle ne remplace ni les cours ni le suivi personnel Notion.

## Objectif

Le wiki Notion doit être un **centre de connaissances et de formation** utilisable au quotidien,
et pas seulement une copie jolie du dépôt. Le dépôt GitHub est la **référence technique**
(code, IaC, CI, décisions, preuves et portfolio). Notion accueille la **présentation pédagogique**,
les cours, l'installation, les exercices, les notes, les difficultés et le suivi de progression.

L'atelier dispose de **sept agents existants**. On les spécialise d'abord par mission
et par critères de recette : aucun huitième « agent Notion » n'est requis tant que
la répartition peut être faite sans duplication. Le chef coordonne ; l'architecte
conçoit la structure ; le rédacteur produit le contenu ; l'auditeur relit
indépendamment les limites et la cohérence ; le DevOps vérifie le code GitHub
quand une procédure s'appuie sur lui.

## Architecture par défaut

```text
Projet / wiki — accueil
├── Comprendre   : contexte, service, architectures, décisions
├── Préparer     : inventaire, installation conditionnelle, vérifications
├── Pratiquer    : méthode, fiches de cours, exercices, indices
├── Suivre       : travail personnel, observations, preuves, autonomie
└── Ressources   : runbooks, glossaire, approfondissements, archives
```

Adapter les cinq espaces à chaque projet. **Ne pas** créer un second suivi,
dupliquer les exercices, renommer des fichiers GitHub pour les rendre « jolis »,
ou produire un dépôt par phase d'apprentissage. Les pages enfants, bases et
liens de l'existant sont à préserver.

## Identité visuelle native

- Une image de présentation originale et une icône sobre pour la page d'accueil.
- Titre clair + accroche (but, utilisateur, portée) + état réel daté.
- Deux colonnes uniquement pour navigation, repères et comparaisons courtes ;
  les cours longs utilisent une colonne lisible sur ordinateur et mobile.
- Quelques callouts ayant un sens stable : bleu (contexte), gris (repère),
  jaune (précaution), violet (méthode). Pas de bloc sans valeur documentaire.
- Table des matières automatique pour les fiches longues ; pas de barre de navigation
  artificielle en doublon des vraies sous-pages.
- Schémas graphiques avec légende : vue de présentation ≠ vue technique ;
  fichier draw.io/SVG source référencé, architecture « cible » ≠ architecture observée.
- Titres H2/H3 hiérarchisés, paragraphes aérés, tableaux pertinents seulement.
  Repérer les intitulés répétés et les blocs de code non fermés avant publication ;
  contrôler manuellement les commandes, la préparation et le résultat attendu.
- Tester le rendu natif, le texte, les images et l'ordre d'empilement mobile.
  **Un fichier Markdown correct n'est pas une vérification visuelle de Notion.**

## Bibliothèque des sept gabarits

| Modèle | Sections indispensables |
| --- | --- |
| Accueil | Bannière, accroche, commencer ici, repères, navigation, architecture, progression, GitHub, état et limites |
| Architecture | Besoin, schéma présentation, schéma technique, flux/ports, ADR, risques, validation |
| Installation | Utilité, environnement, inventaire de l'existant, installation conditionnelle, vérification, dépannage, rollback |
| Cours/exercice | Situation, objectifs, concepts, schéma, exemple distinct, installation, énoncé, indices, contrôles, bilan |
| Runbook | Symptômes, impact, prérequis, hypothèses, tests, intervention, retour arrière, reprise vérifiée |
| Journal | Date/cible, hypothèses, commandes réellement exécutées, observations, blocages, aide, preuves, suite |
| Portfolio | Besoin, réalisation propre, code/commits, tests réels, limites, preuves, démonstration, formulation CV |

Les exemples natifs dans `templates/notion/` sont des **gabarits vierges**.
Ils ne prouvent aucune compétence, ne fixent aucun statut et ne sont pas des
copies de notes privées.

## Navigation et références

1. La page d'accueil ouvre les cinq espaces ; un lecteur doit savoir commencer
   en dix secondes sans explorer tout le sommaire.
2. Les pages d'exercice affichent un accès à l'accueil, aux prérequis, à la
   base de suivi et à la prochaine étape sans dévoiler le corrigé.
3. Les versions, fichiers, ports et commandes renvoient au dépôt GitHub **dans
   sa version réellement consultée** ; lire le contrat et STATUS.
4. L'espace Suivre est l'unique journal des réalisations personnelles.
   Une source CI du projet fourni n'attribue ni niveau L2 ni L3.
5. Les notes privées et aides reçues restent Notion/local. Leur publication
   ou transfert cloud n'est jamais déduit d'un accord sur le code public.

## Répartition des rôles existants

| Agent | Mission wiki |
| --- | --- |
| Chef des opérations | Périmètre, validation des sources, répartition des travaux et demandes d'accord |
| Architecte solutions | Navigation, différences entre modèles, architecture des informations et schémas |
| Rédacteur pédagogique | Rédaction précise et lisible, sections, commandes commentées, cohérence de ton |
| Ingénieur DevOps | Vérification de la cohérence avec le dépôt, installations et contrôles techniques |
| Ingénieur sécurité | Secrets, accès aux notes, protection des environnements, exposition involontaire |
| Expert recherche | Documentation officielle des technologies, dates et liens de référence |
| Auditeur qualité | Diff, sous-pages/bases intactes, liens, exactitude, preuves, lisibilité et rendu contrôlé |

## Protocole de modification

1. Lire la page et identifier les blocs, bases, sous-pages, médias et liens à conserver.
2. Préparer une **prévisualisation** du changement et un inventaire de conservation ;
   privilégier les modifications ciblées, jamais l'effacement du contenu existant.
3. L'utilisateur valide le périmètre et les actions distantes. Une lecture Notion
   n'autorise ni sa réécriture ni sa transmission au cloud.
4. Appliquer seulement les changements approuvés ; garder les liens et contenus non visés.
5. Relire les pages Notion ; contrôler l'image et le sommaire, la navigation, les
   liens GitHub, les tableaux, les blocs de code, la lecture mobile et les avertissements.
6. Séparer `STRUCTURE_VERIFIEE`, `RENDU_VISUEL_VERIFIE` et
   `TECHNIQUE_EXECUTEE` ; n'inventer aucun de ces verdicts.

## Conditions de blocage (« fail-closed »)

Refuser ou demander correction avant d'annoncer un wiki final lorsque :
- la suppression ou le déplacement de sous-pages/bases n'est pas explicite ;
- l'installation des outils, la vérification ou le dépannage a disparu ;
- une donnée de progression est préremplie sans pratique ;
- un graphique, une sortie de commande ou un statut est présenté comme réel sans preuve ;
- un token, un secret ou une note privée menace d'être publié sur GitHub/cloud ;
- l'agent prétend avoir contrôlé l'affichage Notion sans avoir ouvert le rendu.

## Ce qui est livré aujourd'hui / ce qui ne l'est pas

**Présent :** règles versionnées, deux gabarits natifs, spécialisations des agents
existants et importation en lecture seule de sources choisies via
`clawfedora-sources` (PR #206).

**Ajout ciblé :** le module local [`clawfedora-notion-write`](NOTION_CONTROLLED_WRITES.md)
permet désormais de prévisualiser puis de remplacer un bloc textuel simple existant,
uniquement sous approbation exacte. Cette action utilise une intégration Notion
locale dotée du droit adapté, pas la connexion Notion de ChatGPT.

**Toujours non livré :** éditeur Notion autonome multi-blocs, synchronisation en
direct depuis le chat, mise à jour de la base de suivi, pilotage graphique du
navigateur et validation sur le PC Fedora. Le wiki déjà mis en forme via Notion
n'est pas une preuve d'intégration complète dans l'atelier.
