# Preuves techniques associées aux jalons InfraOps

Cette fonctionnalité complète la [feuille de route de projets longs](PROJETS_LONGUE_DUREE.md)
et l'[historique GitHub](GITHUB_SNAPSHOT_REFRESH.md). Elle est distincte
du mécanisme de vérification des critères de tâches multi-agents
('clawfedora project proof') : les preuves des jalons sont des **reçus
d'observation** ; elles n'accordent aucun PASS à une tâche ou à une compétence.

## Principes

- Un reçu doit être relié à un **jalon existant**, un dépôt GitHub
  déjà lié et un SHA complet correspondant au dernier snapshot enregistré.
- La cible opérationnelle est nommée explicitement : par exemple
  'fedora-hote', 'srv-admin', 'srv-app' ou 'srv-k3s'. Ce sont des
  **exemples**, pas une liste imposée.
- Il est recommandé de fournir une empreinte SHA-256 de l'inventaire de la
  cible avec '--environment-sha256'. Sans cette empreinte, la cible est
  considérée **non épinglée**. Une empreinte auto-déclarée ne prouve pas
  à elle seule l'identité d'une machine.
- Les sorties sont du texte UTF-8, 32 Kio maximum ; elles sont vérifiées
  contre des motifs de secrets courants. Un contrôle visuel humain demeure
  indispensable car la détection de secrets ne peut pas être exhaustive.
- Le journal est **append-only** : chaque nouvelle déclaration possède
  un identifiant et un dossier séparés, sans suppression ou réécriture des
  précédentes. L'empreinte interne détecte des altérations accidentelles ;
  ce n'est **pas** une signature cryptographique externe.
- Aucune commande saisie n'est exécutée par cette fonction.
- Les fichiers de preuve ne sont pas intégrés à la recherche des agents
  ni envoyés automatiquement aux fournisseurs cloud.

## Exemple 1 — Consigner une vérification Terraform

Après avoir exécuté soi-même la commande sur la bonne machine et enregistré
sa sortie textuelle dans 'sortie-terraform.txt' :

~~~bash
# Prévisualisation : aucune écriture dans le projet et aucun accès VM.
clawfedora-milestone-evidence --project-id opsdesk capture \
  --milestone-id exercice-04 \
  --repo mathiasseguincadiche/OpsDesk --commit SHA_GIT_COMPLET_40 \
  --environment srv-admin --environment-sha256 SHA256_INVENTAIRE_CIBLE \
  --kind operator --procedure "terraform plan" \
  --expected "Aucun changement inattendu" \
  --observed "Résultat réellement observé sur srv-admin" \
  --result PASS --output-file sortie-terraform.txt
~~~

Le champ 'operator_outcome=PASS' est **déclaratif**. Il ne signifie pas
que Terraform a été exécuté par l'atelier ou que l'exercice est vérifié.
Recopier l'empreinte 'approval_sha256' renvoyée par l'aperçu, puis
réexécuter **exactement la même commande** en ajoutant :

~~~text
--approve EMPREINTE_SHA256_PREVISUALISATION --apply
~~~

Une sortie modifiée, un SHA GitHub actualisé ou un critère devenu divergent
invalide l'approbation. Les données sont relues sous verrou du worker.

Pour lier facultativement le reçu à un critère numéroté du plan multi-agent,
ajouter '--task-id IDENTIFIANT --criterion NUMERO'. Le rapprochement
reste **informatif** : il ne valide pas le critère. Une modification du plan
entraînera un signalement 'TASK_PLAN_CHANGED'.

## Exemple 2 — Résultat CI officiel

L'import d'un résultat GitHub Actions public est différent d'une observation
manuelle. Le programme interroge l'API officielle en lecture seule et
contrôle le run ID, le dépôt, le SHA et la conclusion du pipeline.

~~~bash
clawfedora-milestone-evidence --project-id opsdesk capture \
  --milestone-id exercice-07 \
  --repo mathiasseguincadiche/OpsDesk --commit SHA_GIT_COMPLET_40 \
  --environment ci-github --kind public-ci --run-id IDENTIFIANT_RUN \
  --procedure "GitHub Actions" --expected "Pipeline terminé avec succès"
~~~

L'aperçu indique 'CI_RUN_SUCCESS_ONLY' uniquement si l'API officielle
confirme 'VERIFIED_RUN_SUCCESS'. En cas d'échec ou de run en cours, la
preuve reste 'NOT_VERIFIED'. Seule la conclusion du pipeline est
authentifiée : **aucune validation des VM, du déploiement, de la reprise
après incident ni de la compétence n'en découle**.

Cette première version importe les runs publics GitHub. Les runs privés
authentifiés demandent une intégration distincte du vérificateur privé déjà
présent dans le dépôt, sans exposer de jeton au modèle.

## Consultez la matrice

~~~bash
clawfedora-milestone-evidence --project-id opsdesk report

# Comparer les reçus à une autre cible et à son nouvel inventaire :
clawfedora-milestone-evidence --project-id opsdesk report \
  --environment srv-admin --environment-sha256 NOUVEAU_SHA256_INVENTAIRE
~~~

La matrice affiche, pour chaque jalon, les reçus, la date, le dépôt/SHA,
le type de preuve, la cible et les motifs de requalification. Le tableau
Projets reprend une **vue récapitulative en lecture seule**. La commande
'!etat' dans Open WebUI montre uniquement le nombre de reçus et de
révisions à requalifier, jamais la sortie brute.

## Conséquences d'un changement de version

Le registre vérifie le dernier SHA GitHub connu. Si un nouveau snapshot est
accepté après la preuve, celle-ci reste disponible mais passe à
'REQUALIFY' avec le motif 'GIT_REVISION_CHANGED'. Le même principe vaut
si la cible ou son empreinte d'inventaire est différente à la consultation,
ou si le plan des critères associés a changé.

Ce suivi ne réécrit **jamais** :
- la feuille de route 'continuous_roadmap.json' ;
- les reçus de critères de tâches 'project_proofs' ;
- les exercices personnels et niveaux L0-L3 ;
- les pages Notion ;
- les fichiers GitHub ou les sorties des VM.

La réception avec une installation Fedora réelle, des VM et un dépôt GitHub
de test est encore distincte des tests automatiques en CI.
