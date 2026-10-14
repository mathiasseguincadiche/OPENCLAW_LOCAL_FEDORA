# Plan de qualité vérifiable — OpenClaw / Fedora / Open WebUI

**Situation :** première installation directement prévue sur Open WebUI **v0.12.1-slim** ;
aucune conversion de 0.11.4 n'est demandée sur une machine encore vierge.
Le téléchargement est verrouillé au digest effectif par Podman avant de générer systemd,
mais l'exécution réelle dans le navigateur Fedora reste **non qualifiée**.
Ce plan ne remplace pas les essais sur le PC cible ni l'état factuel de `STATUS.md`.

## Principes de livraison

- Séparer code écrit, test unitaire passé, intégration conteneur passée, matériel testé et service externe réel testé.
- Aucune mise à jour automatique de modèle, d'image ou de dépendance ; versions et digests exacts.
- Préserver le mode local par défaut, la barrière de confidentialité et le plafond cloud de 25 €.
- Tout changement d'état projet conserve une confirmation humaine indépendante du modèle.
- Un faux fournisseur, une base SQLite simulée ou une CI verte ne valident pas un vrai fournisseur ou un navigateur.

## Travaux déjà intégrés au dépôt (PR #56 et #62)

- [x] Journal cloud : maintenir le coût maximal réservé pour une erreur HTTP ambiguë (408 ou 5xx), comme pour une perte réseau ; tests de régression ajoutés.
- [x] Chat local : accepter jusqu'à quatre pièces jointes de texte/code UTF-8 (12 000 octets cumulés) sans créer de projet, après vérification du stockage Open WebUI ; refuser images, PDF, Office, binaire et cloud.
- [x] Corriger les limites cloud obsolètes dans la documentation de conversation.
- [x] Ajouter un contrôle automatisé des indications documentaires importantes.
- [x] Vérifications CI des PR #56 et #62 : réussies à leur fusion. **Les essais Fedora réels restent à faire**.

## Documentation pédagogique et architecture

La documentation de découverte s'organise maintenant autour du [README](../README.md), du [guide](GUIDE.md), des [sept rôles](fiches/07-roles-et-outils.md), des [flux d'architecture](fiches/11-comment-ca-marche.md) et d'un [exemple DevOps](EXEMPLE_PARCOURS_DEVOPS.md). Les schémas SVG sont des cartes pédagogiques **du fonctionnement prévu**, pas des preuves d'intégration du conteneur ni de la GPU.

## Blocage P0 : qualification réelle sur le PC

1. Déployer sans root sur Fedora 45 Workstation / GNOME 51 avec SELinux Enforcing et la B580.
2. Tester 32K, 16K si nécessaire, vitesse, VRAM, températures et comportement après veille.
3. Exécuter le parcours `docs/SMOKE_TEST_WEBUI.md` dans le vrai navigateur avec le vrai volume uploads.
4. Vérifier que les fichiers sans projet sont lisibles localement, rejetés en cloud et ne créent aucun projet.
5. Tester le vrai OpenRouter avec une clé limitée, sans rechargement automatique : modèle servi, confidentialité, délai, appels d'outils et rapprochement des frais.
6. Simuler interruption, redémarrage, sauvegarde et restauration dans une installation de test.

**Acceptation :** mesures horodatées dans `STATUS.md`, résultats PASS/FAIL
et journaux assainis ; aucune protection désactivée pour obtenir PASS.

## P1 : réception de l'installation initiale Open WebUI 0.12.1

- Configurer **v0.12.1-slim dès la première installation** : aucune migration d'une ancienne base 0.11.4 n'est obligatoire.
- Vérifier le tag stable à la récupération, puis figer dans systemd la référence exacte `ghcr.io/open-webui/open-webui@sha256:...`; ne jamais utiliser `:latest` ni deviner une empreinte.
- Le canary isolé demeure facultatif pour vérifier un conteneur jetable ou une éventuelle copie de base ancienne ; `--with-db-copy` n'est pas exigé sans base existante.
- Vérifier les Functions/Filters sous Open WebUI 0.12.1 et le traitement des fichiers, uploads, actions de projet et STT/TTS.
- Effectuer la réception réelle navigateur/GPU/stockage/SELinux sur Fedora ; ne pas interpréter la seule CI comme une preuve matérielle.

**Acceptation :** premier déploiement par digest valide et expérience navigateur mesurée, pas de migration fictive.

Source officielle : https://github.com/open-webui/open-webui/releases/tag/v0.12.1

## P1 : expérience de conversation

- **Streaming réel** : PR #89 et #90 intégrées ; le transport et le pont WebUI
  savent émettre progressivement depuis OpenClaw sous activation canary privée.
  La voie nominale reste le CLI en un bloc. La vraie réception par Open WebUI,
  l'annulation et le Gateway opérateur sont **à qualifier sur Fedora**, pas
  considérés prouvés par la CI.
- Arrêt explicite : traiter déconnexion et annulation sans libérer un verrou ni oublier un coût encore engagé.
- Chat sans projet : PDF texte et Office bornés ; images limitées aux métadonnées par défaut. **Canary vision Qwen local** disponible sous marqueur 0600 : images ou PDF scannés de 1–2 pages, prévalidation de l'identité Qwen et verrou commun, aucune route cloud ni fallback. Les tests automatisés ne prouvent pas la qualité OCR/vision ni les performances de la B580 ; qualifer dans le navigateur sur un jeu d'exemples de référence.
- Ne jamais faire d'un fichier joint ou d'un message du modèle une confirmation humaine.

**Acceptation :** test de réception des premiers tokens avant fin d'inférence ;
arrêt/redémarrage reproduits ; aucune commande système déclenchée par une pièce jointe.

## P1 : documents et schémas professionnels

- Document Markdown source, styles PDF/DOCX cohérents, tableaux complexes, blocs de code lisibles, illustrations/diagrammes et sommaire si nécessaire.
- Génération longue par sections avec assemblage atomique, provenance et vérification d'intégrité.
- Schémas Draw.io : source native désormais générée en 1 à 8 vues indépendantes, chaque vue limitée à 8 blocs et 12 liens ; aperçu SVG limité à la première vue et explicitement identifié. La qualité visuelle reste à vérifier manuellement dans l'éditeur.
- Tests de rendu de référence et contrôle des artefacts PDF/DOCX/Draw.io produits ; aucune promesse de qualité sans inspection visuelle.

**Acceptation :** un runbook complet, une architecture multi-zones et un rapport d'audit exportés sans troncature, avec sources éditables.

## Préparer une évaluation métier reproductible

La CLI `clawfedora-evals` génère un plan de **sept scénarios publics et synthétiques** couvrant les sept rôles, puis agrège des **notes humaines et des références de preuves complètes**. Elle n'appelle aucun modèle et ne se présente pas comme un benchmark déjà exécuté. Les comparaisons Qwen vs DeepSeek et la vérification humaine des sorties restent à réaliser dans la dernière phase.

→ [Mode d'emploi des évaluations](EVALUATION_AGENTS.md) · [Programme global](PROGRAMME_AMELIORATION_2026.md).

## Mesurer l'efficacité réelle de Qwen + DeepSeek

La stratégie du projet est **hybride par conception** : Qwen quotidien, DeepSeek pour les tâches difficiles, sans routage automatique tant que ce mécanisme n'est pas conçu et validé.

- Comparer **sur les mêmes tâches DevOps publiques** un module Terraform multi-fichiers, une revue CI, un ADR, un audit de configuration et un runbook complexe.
- Mesurer **correction technique, qualité pédagogique, nombre de reprises, temps total, coût réel et confidentialité** ; ne pas inférer la supériorité de DeepSeek d'un contexte maximal plus grand.
- Vérifier les deux cas actuels : choix du modèle dans le chat, et **accord cloud appliqué au projet** dans l'atelier. Une sélection par tâche/agent n'existe pas encore.
- Évaluer ultérieurement un routage assisté **avec consentement explicite, critère de coût, règles de non-divulgation et journal d'explication du choix**, sans jamais rendre automatique l'envoi de documents privés.

→ [Contrat pédagogique du système hybride](ARCHITECTURE_HYBRIDE.md).

## Laboratoire DevOps — première étape de code

Une commande `clawfedora-lab` est maintenant disponible comme **exécuteur standalone**, hors des outils OpenClaw : dry-run obligatoire par défaut, `--apply` humain, image locale épinglée par digest, copie filtrée et temporaire, réseau absent et conteneur rootless en lecture seule. Elle prévoit `terraform fmt/validate`, `ansible-lint`, `actionlint`, `shellcheck` et `hadolint`.

**Le validateur annexe n'est pas un laboratoire Rocky obligatoire :**
OpenClaw tourne sur Fedora indépendamment de cet outil. Si le validateur
facultatif est utilisé, image OCI de base librement choisie, versions,
provenance et vrais tests Podman restent à qualifier.
[Précisions](LABORATOIRE_DEVOPS.md).

## Provenance des pipelines GitHub/GitLab publics

La commande `clawfedora-ci-proof` récupère uniquement **l'état global d'une
exécution CI publique** dans les API officielles avec SHA/identifiant vérifiés.
Aucun token, journal ou accès privé n'est transmis. Elle reste distincte des
outils de l'auditeur et des preuves d'exécution sur un laboratoire réel.
[Mode d'emploi et limites](PREUVES_CI_GITHUB_GITLAB.md).

L'authentification à des projets privés sous permissions minimales, les
preuves de jobs/artefacts et l'intégration contrôlée au moteur des projets
restent à développer.

## Recherche documentaire : fraîcheur des preuves

Le contexte de projet envoyé aux agents n'inclut plus les passages de
recherche expirés. Si l'intégrité de l'intake a dérivé depuis sa capture,
les anciens extraits de l'index FTS sont exclus et le contexte indique
`source_integrity=UNVERIFIED_CHANGED` : il faut reconstruire l'index avant
de citer. Les références conservées incluent le chemin, la page et la ligne
quand ces informations sont disponibles. Cette vérification automatique
ne remplace ni une recherche humaine ni l'examen du document original.

## P2 : ergonomie et vérification métier

- Le plugin Action expose désormais **cinq lectures locales** (projets, état,
  aide, modèle, budget), **huit transitions de projet** avec confirmation
  navigateur et **trois formulaires** (création, précision, révision).
  La création et la révision exigent encore leur code d'approbation
  indépendant. Les dialogues sont testés hors navigateur ; leur rendu
  réel sur Open WebUI reste à qualifier. Un formulaire dédié à la
  soumission de fichiers reste à faire.
  Toute action doit passer par les mêmes API déterministes et confirmations à usage unique.
- **Priorité :** finaliser le vrai streaming d'Open WebUI sur Fedora
  et les commandes visuelles de projet avec approbation humaine,
  sans accès libre des agents à la machine.
- **Option séparée uniquement si souhaitée :** qualifier le validateur
  CLI déjà préparé dans une image OCI à base libre, avec quotas
  et **aucun accès en écriture au projet original** ; jamais une VM
  Rocky imposée au fonctionnement d'OpenClaw.
- Ajouter une validation distincte pour les citations/documentations officielles et
  envisager un second modèle auditeur uniquement si le budget l'autorise.
- Évaluer Qwen contre DeepSeek sur les mêmes cas DevOps avec critère de correction
  technique, pédagogie, latence et coût. Ne pas déduire la compétence d'un simple PASS.

**Acceptation :** critères métier reproductibles, intervention humaine explicite
et qualité démontrée sur de vrais scénarios.

## Critère final

Le projet ne devient « prêt pour un usage quotidien validé » qu'après :

- CI verte sur le commit livré ;
- qualification PC Fedora, conteneur Open WebUI et API réelle ;
- sauvegarde/restauration vérifiées ;
- parcours utilisateur sans régression bloquante ;
- limites résiduelles clairement publiées dans `STATUS.md`.

Une fonctionnalité demandée n'est jamais marquée implémentée parce qu'elle apparaît dans ce plan.
