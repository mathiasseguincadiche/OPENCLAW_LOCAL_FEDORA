# Méthodes V26 adaptées à ClawFedora — sans Skills

Ce lot reprend **des méthodes** de la collection « Prompts de projets V26 »
et les transpose aux sept agents et outils préexistants. **Aucun module
V26 brut ni Skill n'est copié ou chargé dans les workspaces.** Les compétences
techniques et les droits d'administration existants sont inchangés.

## 1. Évolution ciblée des sept rôles

- Le **chef** choisit le travail utile (DIRECT, MENTOR, AUDIT, RÉALISATION)
  sans changer `practice_opt_in` ni contourner le plan humain ; il peut
  proposer une passation avec `clawfedora_outline kind=handover`.
- La **recherche** distingue mieux version installée, annonce, documentation
  actuelle et essai réellement nécessaire.
- L'**architecte** dispose de `service_contract`, de compositions adaptées
  et d'une revue des supports à actualiser.
- Le **DevOps** dispose d'`operations_acceptance`, de scénarios proposés
  (restauration, rollback, incident, accès...) séparés du lint.
- La **sécurité** proportionne les décisions au contexte réel sans affaiblir
  SELinux, le pare-feu ni les approbations.
- Le **rédacteur** prépare une revue des parcours de lecture et conserve
  les sections d'installation des outils.
- L'**auditeur** exige la preuve d'un défaut avant de proposer une refonte ;
  il sait préserver un élément déjà satisfaisant.

Les règles communes de provenance, de non-exécution et de lecture seule
restent en vigueur.

## 2. Schémas Draw.io/SVG : composition explicite

`clawfedora_diagram` accepte des champs **facultatifs**, par page :

| Paramètre | Valeurs | Fonction |
| --- | --- | --- |
| `layout` | `column`, `flow`, `zones` | Vertical compatible, parcours en grille ou frontières nommées en colonnes |
| `node_types` | `component`, `person`, `host`, `service`, `database`, `security`, `monitoring`, `backup`, `pipeline` | Formes et couleurs liées au type |
| `edge_types` | `application`, `administration`, `monitoring`, `backup` | Couleurs de flux différenciées |
| `boundaries` | Une vraie zone par nœud, si connue | Le mode `zones` dessine des groupes indépendants |

Sans paramètres nouveaux, le diagramme historique reste en `column`.
Chaque vue additionnelle peut choisir sa composition. Le SVG est généré
à partir de la même géométrie que le XML Draw.io (ancrages recalculés,
libellés bornés, largeur du canevas adaptée).

Exemple de proposition pour l'architecte :

~~~json
{
  "title": "Chaîne d'administration",
  "layout": "flow",
  "nodes": ["Git", "Pipeline CI", "API", "Base de données"],
  "node_types": ["component", "pipeline", "service", "database"],
  "edges": [[0, 1], [1, 2], [2, 3]],
  "edge_types": ["administration", "administration", "application"],
  "edge_labels": ["commit", "image OCI", "SQL"]
}
~~~

Le mode `zones` requiert au moins deux groupes effectivement distincts ;
`flow` refuse les frontières nommées plutôt que les ignorer. Les limites
actuelles restent **8 nœuds et 12 liens par vue**. Le XML est structurellement
contrôlé, **pas** la justesse de l'infrastructure. La lisibilité native
Draw.io, le rendu Notion, GitHub en clair/sombre et sur mobile demandent
encore une recette réelle : ne pas les déclarer certifiés par la CI.

## 3. Changement technique → revue documentaire ciblée

`clawfedora_impact` prépare une liste de relecture **dans un snapshot local
autorisé**, sans accès réseau, GitHub distant ni Notion distant. Il relève
les références Markdown ou mentions littérales constatées, plus quelques
fichiers potentiellement affectés par type de source.

Entrée de l'outil :

~~~json
{
  "scope": "projects/exemple",
  "changed_paths": ["docs/diagrams/architecture.drawio", "compose.yaml"]
}
~~~

Usage indépendant en terminal sur une copie de projet **déjà disponible** :

~~~bash
python -m clawfedora.document_impact --path /chemin/du/snapshot \
  --changed docs/diagrams/architecture.drawio --changed compose.yaml
~~~

La sortie vaut `REVIEW_QUEUE_NOT_SYNCHRONIZATION` :
- `direct_references` signifie une occurrence **lue**, pas une contradiction ;
- `potential_review` signifie un fichier à vérifier, pas un défaut prouvé ;
- `NOT_CHECKED` peut signifier source absente du snapshot partiel ;
- chaque page ou image Notion reste `NOT_CHECKED_EXPLICIT_EXPORT_REQUIRED`.

**Ne jamais** modifier automatiquement Notion après un changement GitHub :
la source technique, les images publiées et les notes privées ont des droits
et des cycles de validation distincts. Prévisualiser le diff, obtenir un
accord ciblé, relire le rendu réel.

## 4. Quatre situations de consultation documentaire

Le nouvel outil `clawfedora_doc_review`, réservé au rédacteur et à
l'auditeur, prend un contenu Markdown borné (`content`) et un `kind` parmi
`readme`, `procedure`, `course`. Il relève la hiérarchie de titres et
les **indices** de rubriques attendues, puis prépare quatre épreuves :

1. Première découverte (premier écran).
2. Apprentissage de bout en bout (préparation, résultat attendu).
3. Recherche ciblée (port, décision, procédure de restauration).
4. Analyse experte (choix, compromis, preuve rattachée).

**Toutes les épreuves reviennent `NOT_EVALUATED` tant qu'un lecteur ou
une recette visuelle n'a pas été réellement observé.** Un titre présent
ne signifie pas que son contenu est exact. Un titre absent peut être
volontaire pour une réponse courte. Le contrôle n'attribue ni note
arbitraire ni verdict éditorial PASS.

## 5. Passation et validation opérationnelle

L'architecte, le chef et le DevOps disposent de trames facultatives
pour l'artefact livré (version/digest), les prérequis, ports, dépendances,
secrets, diagnostics, sauvegardes, rollback et critères de réception.

`clawfedora_lab_request` peut aussi recevoir, **en plus** de son validateur
statique habituel, un `scenario` parmi :

`reprovision`, `idempotence`, `incident`, `restore`, `rollback`,
`access-control`, `performance`, `resilience`.

Il faut alors décrire la `target`, l'`initial_state`,
l'`expected_observation`, la `stop_condition` et la `recovery`.
La réponse ajoute un `scenario_plan` à l'état
`PROPOSED_NEEDS_OPERATOR_EXECUTION` avec `proof=NOT_COLLECTED`.

**Important :** le reçu du validateur statique ne prouve jamais la
réussite du scénario opérationnel. Aucune VM, service, application ou
backup n'est manipulé par cette nouvelle option. L'exécution et la
preuve sur une cible réelle nécessitent des commandes/receipts opérateur
et les autorisations déjà imposées par ClawFedora.

## 6. Réception et limites

La CI valide les chemins, la structure Draw.io, les bornes de l'API, le
routage des outils et leur lecture seule. La réception finale exige
aussi une **exécution sur Fedora** et l'inspection des SVG dans Draw.io,
GitHub et Notion aux formats concernés.

Ce lot **n'installe aucun Skill**, ne change pas de modèle, n'ajoute pas
d'agent, ne donne pas d'outil shell aux LLM, ne republie pas les notes
Notion et ne prétend pas produire les 20 compositions graphiques V26
de l'archive. Les améliorations de composition sont délibérément
progressives et conservent l'ancien générateur comme repli explicite.

À chaque correction ultérieure : établir le problème et sa preuve,
le gain, le risque, la non-régression et **la condition d'arrêt**.
Un élément correct peut et doit être conservé.
