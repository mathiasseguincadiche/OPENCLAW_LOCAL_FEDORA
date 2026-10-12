# Plan de qualité vérifiable — OpenClaw / Fedora / Open WebUI

**Situation :** la version actuellement épinglée est Open WebUI v0.11.4. La v0.12.0 est
publiée depuis le 10 octobre 2026, mais **pas encore validée** dans ce projet.
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

1. Déployer sans root sur Fedora 44 avec SELinux Enforcing et la B580.
2. Tester 32K, 16K si nécessaire, vitesse, VRAM, températures et comportement après veille.
3. Exécuter le parcours `docs/SMOKE_TEST_WEBUI.md` dans le vrai navigateur avec le vrai volume uploads.
4. Vérifier que les fichiers sans projet sont lisibles localement, rejetés en cloud et ne créent aucun projet.
5. Tester le vrai OpenRouter avec une clé limitée, sans rechargement automatique : modèle servi, confidentialité, délai, appels d'outils et rapprochement des frais.
6. Simuler interruption, redémarrage, sauvegarde et restauration dans une installation de test.

**Acceptation :** mesures horodatées dans `STATUS.md`, résultats PASS/FAIL
et journaux assainis ; aucune protection désactivée pour obtenir PASS.

## P1 : mise à niveau Open WebUI 0.12.0

- **Ne pas** remplacer le digest de v0.11.4 par un tag mouvant ou une empreinte devinée.
- Recueillir le digest officiel de l'image `slim` cible et tester son démarrage dans un volume jetable ; la commande `bash scripts/linux/14_webui_canary.sh --apply [--with-db-copy]` prépare désormais cette préqualification.
- Tester la migration SQLite depuis une copie cohérente de v0.11.4 et la possibilité de restaurer. Le canary `--with-db-copy` contrôle désormais la présence des tables et la conservation des comptes, conversations et fonctions (contenu/activation) dans la base jetable ; il refuse de conclure PASS si une de ces données disparaît.
- Vérifier l'activation explicite des Functions/Filters : la v0.12.0 introduit `ENABLE_PLUGINS` comme interrupteur maître. Les variables `ENABLE_PLUGINS=true`, `ENABLE_FUNCTIONS=true` et `ENABLE_TOOL_SERVERS=false` sont désormais explicites dans la configuration générée.
- Tester l'insertion du filtre `clawfedora_files`, `file_handler`, la résolution des chemins, l'appartenance utilisateur et chaque type d'upload.
- Tester STT/TTS et s'assurer qu'aucun mode vocal distant ne s'active par défaut.
- Mettre à jour version et digest ensemble dans `config/webui_policy.yaml`; passer tout le smoke test.

**Acceptation :** pas de migration destructive, aucun RAG parallèle, tests
d'intégration réels et retour arrière documenté.

Source officielle : https://www.openwebui.com/blog/v0-12-0-a-voice-that-talks-back-and-a-face-to-go-with-it

## P1 : expérience de conversation

- **Streaming réel** : PR #89 et #90 intégrées ; le transport et le pont WebUI
  savent émettre progressivement depuis OpenClaw sous activation canary privée.
  La voie nominale reste le CLI en un bloc. La vraie réception par Open WebUI,
  l'annulation et le Gateway opérateur sont **à qualifier sur Fedora**, pas
  considérés prouvés par la CI.
- Arrêt explicite : traiter déconnexion et annulation sans libérer un verrou ni oublier un coût encore engagé.
- Chat sans projet : étendre l'analyse isolée aux PDF/Office/images avec la **même** ingestion contrôlée, sans raccourci direct vers le cloud.
- Ne jamais faire d'un fichier joint ou d'un message du modèle une confirmation humaine.

**Acceptation :** test de réception des premiers tokens avant fin d'inférence ;
arrêt/redémarrage reproduits ; aucune commande système déclenchée par une pièce jointe.

## P1 : documents et schémas professionnels

- Document Markdown source, styles PDF/DOCX cohérents, tableaux complexes, blocs de code lisibles, illustrations/diagrammes et sommaire si nécessaire.
- Génération longue par sections avec assemblage atomique, provenance et vérification d'intégrité.
- Schémas Draw.io multi-vues : dépasser les limites actuelles de huit blocs et douze flèches par génération sans produire de diagrammes illisibles.
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
