# Préparer une PR GitHub pendant un projet InfraOps en cours

Le moteur multi-agent **ne change pas** : ses validations, ses livrables
finaux et sa règle de publication après l'état COMPLETE demeurent en place.

Cette fonction permet à l'opérateur de proposer une **correction ponctuelle
depuis un jalon actif** (par exemple une évolution Terraform d'OpsDesk),
sans clôturer le projet et sans déclarer l'exercice vérifié.

## Prérequis

- Projet ClawFedora déjà créé, sources initiales scellées et **snapshot
  GitHub lié**. Le dernier SHA approuvé via
  'clawfedora-github-refresh' peut servir de base.
- Projet en état IN_PROGRESS, VALIDATING ou REVIEW et jalon de la feuille
  de route en état IN_PROGRESS ou BLOCKED.
- Code déjà préparé et relu par l'utilisateur dans
  'projects/<projet>/work/github-pr/<jalon>/'.
- Sous ce dossier, **les chemins sont relatifs à la racine du dépôt GitHub**.
  Exemple : 'infra/main.tf' et 'docs/runbook.md'.
- Le dépôt doit toujours avoir ce SHA sur 'main' à la publication.
  Si la branche principale a avancé, actualiser d'abord la source via
  le mécanisme des snapshots. Une proposition ancienne est refusée.

Les fichiers explicitement autorisés sont limités à 15. Le collecteur
réutilise les protections de la publication GitHub existante : fichiers
texte UTF-8, volume borné, interdiction des symlinks, chemins sensibles,
secrets connus et workflows GitHub Actions (interdits dans ce mode).

## Prévisualisation locale

~~~bash
# Aucune connexion GitHub et aucune écriture distante.
# Fournir le SHA complet 40 caractères du dernier snapshot GitHub.
clawfedora-github-work-pr \
  --project-id mon-projet --repo mathiasseguincadiche/OpsDesk \
  --base-sha <SHA40> --branch atelier/terraform-correctif \
  --milestone-id exercice-04 \
  --file infra/main.tf --file docs/architecture.md
~~~

La commande vérifie les chemins choisis, compare les fichiers stagés au
snapshot local et affiche un diff textuel borné (160 lignes au plus).
Une modification inchangée est refusée. **Les suppressions de fichiers ne
sont pas encore prises en charge**.

La réponse contient 'approval_sha256', qui identifie le projet, la
version du jalon, le dépôt, le SHA, la branche et les contenus. Une
modification ultérieure exige une nouvelle prévisualisation.

## Publication après approbation explicite

Enregistrer un texte de PR (sans token ni information confidentielle)
dans un fichier local, puis :

~~~bash
clawfedora-github-work-pr \
  --project-id mon-projet --repo mathiasseguincadiche/OpsDesk \
  --base-sha <SHA40> --branch atelier/terraform-correctif \
  --milestone-id exercice-04 \
  --file infra/main.tf --file docs/architecture.md \
  --title "Corriger la configuration Terraform" \
  --body-file description-pr.md \
  --approve-repo mathiasseguincadiche/OpsDesk \
  --approve-sha256 <EMPREINTE_DE_L_APERÇU> --apply
~~~

Un 'GITHUB_TOKEN' local est requis uniquement pour publier.
La fonction refuse les branches existantes, les commits de base devenus
obsolètes et les approbations divergentes. Elle réutilise
'github_pr.publish_draft' pour créer **uniquement une branche et une PR
brouillon** ; aucune fusion n'est déclenchée.

Chaque tentative est consignée avant l'écriture distante. En cas d'échec
ambigu, ne relancez pas automatiquement : vérifiez la branche et la PR
sur GitHub avant de constituer une nouvelle proposition.

## Depuis le chat Open WebUI

Dans une conversation ayant un projet ClawFedora sélectionné :

~~~text
!github travail-pr owner/repo SHA40 atelier/branche exercice-04 infra/main.tf,docs/architecture.md
!github publier-travail owner/repo EMPREINTE_SHA256
~~~

Le pont gère ces deux commandes lui-même : **le modèle IA ne peut
pas signer l'approbation**. La seconde commande est réservée à un rôle
local. Pour examiner le diff complet avant publication, utiliser
la commande CLI. Le classement d'une conversation dans un dossier
Open WebUI ne sélectionne pas à lui seul le projet ClawFedora.

## Ce que cette fonction ne prouve pas

- Une PR créée n'atteste ni CI verte, ni exécution sur les VM, ni
  maîtrise d'une compétence.
- Le jalon garde 'NOT_VERIFIED' et ne passe pas automatiquement en
  IMPLEMENTED.
- Les snapshots GitHub et les preuves existantes ne sont pas réécrits.
- Les nouveaux commits et les preuves restent à qualifier selon leurs
  propres critères avant toute fusion ou mise à jour documentaire.
- Il n'y a aucun SSH libre, 'terraform apply' autonome ou exécution
  de code du dépôt par les agents.

La fonctionnalité est conçue pour un usage humain explicite et des
propositions incrémentales, sans modifier le parcours de publication
des livrables déjà terminés.
