# Projets InfraOps de longue durée : feuille de route persistante

L'atelier conserve son moteur de projet court (cadrage, plan de 1 à 4 tâches,
revue et livraison). Pour un projet évolutif comme OpsDesk, une **feuille de
route indépendante** permet de suivre plusieurs dizaines de jalons dans
**le même projet ClawFedora**. Cette fonctionnalité ne remplace ni les tâches
des agents, ni GitHub, ni Notion.

## Initialiser une feuille de route

Créer un projet dans l'atelier comme d'habitude. Préparer un fichier JSON
local (exemple synthétique, **pas un état vérifié d'OpsDesk**) :

~~~json
{
  "milestones": [
    {"id": "exercice-01", "title": "Comprendre le contrat", "depends_on": []},
    {"id": "exercice-02", "title": "Concevoir le réseau", "depends_on": ["exercice-01"]},
    {"id": "exercice-03", "title": "Préparer Linux", "depends_on": ["exercice-02"]}
  ]
}
~~~

Une feuille de route contient de 1 à 100 jalons, des titres courts, des IDs
stables et des dépendances sans cycle. Les dépendances peuvent pointer sur
un jalon déclaré plus loin dans le JSON.

~~~bash
# Prévisualisation : aucune écriture
clawfedora project roadmap-init --project-id mon-projet --file parcours.json

# Initialisation explicite, sous verrou du worker
clawfedora project roadmap-init --project-id mon-projet --file parcours.json --apply

# Lire le suivi ; inclut les notes et l'historique des changements
clawfedora project roadmap --project-id mon-projet

# Prévisualiser un changement
clawfedora project roadmap-set --project-id mon-projet \
  --milestone-id exercice-01 --state IN_PROGRESS --note "Laboratoire préparé"

# Écrire après revue
clawfedora project roadmap-set --project-id mon-projet \
  --milestone-id exercice-01 --state IN_PROGRESS --note "Début personnel" --apply
~~~

États disponibles : **PLANNED**, **IN_PROGRESS**, **BLOCKED** et
**IMPLEMENTED**. Un jalon ne peut devenir IMPLEMENTED que si ses
dépendances le sont déjà. Les changements sont enregistrés avec date et note.
La feuille de route n'est **jamais écrasée implicitement** par une nouvelle
initialisation.

## Ce que ces états prouvent (et ne prouvent pas)

**IMPLEMENTED signifie uniquement « déclaré réalisé par l'opérateur »**.
Le champ de contrôle demeure toujours **NOT_VERIFIED**. Seules les
vérifications indépendantes, avec leurs sorties réelles, peuvent contribuer
à une qualification technique. Les niveaux d'apprentissage L0-L3 de Notion
ne sont pas attribués par cet outil.

La feuille de route est stockée dans
'projects/<identifiant>/context/continuous_roadmap.json'.
Elle n'altère pas 'project.json', les tâches du plan multi-agent, les
sources figées ni les contrôles cloud. Les conversations Open WebUI gardent
leur propre historique : le contexte du projet doit toujours être sélectionné.

Le tableau de bord Projets présente les jalons en **lecture seule** dans le
dossier ouvert ; la création et les changements d'état passent toujours par
la CLI et ses confirmations.

Pour examiner les changements entre deux commits GitHub au cours d'un
parcours long, consulter [Actualiser les snapshots GitHub](GITHUB_SNAPSHOT_REFRESH.md).
La nouvelle version est conservée séparément, sans modifier les exercices
ni les preuves existantes.

Les correctifs d'un exercice en cours peuvent être préparés sous forme
de [PR brouillon liée au jalon](GITHUB_PR_PROJET_EN_COURS.md), après revue
de diff, vérification du SHA GitHub et approbation explicite. Cette opération
ne certifie pas l'exercice et ne modifie pas sa progression.

Les [preuves d'exécution par jalon](PREUVES_JALONS_INFRAOPS.md)
sont conservées séparément et liées à une cible et un SHA GitHub précis.
Elles ne changent pas les états d'apprentissage et deviennent à requalifier
lorsqu'un nouveau code, une nouvelle cible ou un plan modifié invalide
leur portée.

**Limites de cette première tranche :** pas de saisie graphique, pas
d'actualisation GitHub/Notion, pas de
synchronisation des preuves, pas d'exécution sur Fedora ou sur les VM Rocky.
Une évolution ultérieure pourra associer chaque jalon à un SHA Git et à
des preuves explicites, sans créer de deuxième source de vérité.
