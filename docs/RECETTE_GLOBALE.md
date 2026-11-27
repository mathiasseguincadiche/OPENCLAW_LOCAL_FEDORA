# Recette globale de ClawFedora — Atelier natif

## Objectif et périmètre

La réception couvre Fedora 45 Workstation / GNOME 51 sous Wayland, le
stockage secondaire, la B580, OpenClaw et Ollama, Qwen 3.5 9B et Ornith
1.5 9B, les sept rôles, les projets et les cinq pages de l'Atelier.
L'inférence reste locale. GitHub, Notion et la recherche Web restent
des intégrations distantes distinctes ; aucune clé de fournisseur de
modèles cloud n'est nécessaire. Open WebUI n'est pas une dépendance
de l'Atelier natif.

Le dépôt peut être développé, audité et testé en CI avant installation.
Cette recette ne prétend pas que le PC a déjà été testé.

## 1. Trois modes sans inférence

Depuis le dépôt, avec le venv du projet disponible :

```bash
./menu.sh --action acceptance-plan
./menu.sh --action acceptance-source
```

Le premier imprime le parcours et les preuves attendues, sans contrôle
du poste. Le second vérifie les contrats du dépôt. Les suites CI
Python, Ruff, Mypy, ShellCheck, CodeQL, navigateur synthétique et
contrats Fedora restent complémentaires ; un contrat valide ne signifie
pas que toutes ces suites ont été exécutées.

**Après installation seulement**, depuis la session graphique :

```bash
./menu.sh --action acceptance-inspect
```

Équivalent CLI, adapter le chemin au runtime effectivement installé :

```bash
clawfedora-acceptance --root "$PWD" --inspect --runtime-root /data/IA/Openclaw
```

Le précontrôle réemploie la validation du stockage, le contrôle système
et le bilan de santé sans sonde d'inférence. Il contrôle les services
natifs actifs et activés, les versions et identités des modèles,
SELinux/firewalld, la B580/Vulkan, les limites effectives d'inférence
et la disponibilité HTTP des cinq pages. Une page disponible ne
prouve pas que son interface ou sa connexion externe fonctionne.
Les sondes d'inventaire et de pages sont des GET sur des destinations
loopback fixes, sans proxy ni suivi de redirection.

Aucun téléchargement de modèle, lancement de génération, changement
de profil, sauvegarde ou action GitHub/Notion n'est déclenché.
Les sorties détaillées des commandes ne sont pas recopiées dans le
rapport. Le résultat JSON n'est pas une attestation signée : il
contient des statuts et l'heure de l'observation, pas de preuve
d'identité de la machine ni de validation d'une autre installation.

| Précontrôle | Sens |
| --- | --- |
| NOT_RUN | Plan seulement |
| SOURCE_CONTRACTS_PASS | Contrats du dépôt vérifiés |
| BLOCKED | Dépôt ou stockage non admissible ; arrêt des sondes |
| REVIEW_REQUIRED | Échec ou avertissement du précontrôle ; diagnostiquer |
| READY_FOR_MANUAL_TESTS | Précontrôle favorable, poursuivre les essais |

Tous les modes gardent le verdict `NOT_END_TO_END_QUALIFIED`.
Les étapes actives de la campagne restent `NOT_RUN`. Ne pas publier
un rapport contenant des données personnelles ou des secrets.

## 2. Installation et premier fonctionnement

Suivre le [Live USB](LIVE_USB_FEDORA45_PREQUALIFICATION.md) si souhaité,
puis l'[installation simple](INSTALLATION_SIMPLE_FEDORA45.md).
Vérifier l'ISO officielle, le deuxième disque EXT4 monté sur /data et
le passage du précheck avant toute installation. Ne pas reformater un
disque contenant des données.

Après le précontrôle installé :

```bash
./menu.sh --action quick-check
```

Cette commande réalise de courtes inférences locales sous le verrou du worker :
elle n'est pas exécutée par le mode inspect. Examiner le résultat des deux modèles.
Ouvrir l'Atelier à `http://127.0.0.1:18890` et conserver des preuves
datées, sans clés ni données privées.

## 3. Sept rôles et déroulement de projet

Utiliser un projet synthétique isolé, jamais le dépôt OpsDesk de
production pour les essais de mutation. Préparer les cas synthétiques
avec `clawfedora-evals --plan` et la grille pédagogique avec
`clawfedora-pedagogy --plan`.

| Rôle | Contrôle réel à effectuer |
| --- | --- |
| Mentor / chef d'opérations | Compréhension, clarification et plan de travail |
| Expert recherche | Recherche autorisée, sources exactes et citations |
| Architecte solutions | Choix justifiés, schéma SVG et Draw.io |
| Ingénieur DevOps | Code, test volontairement en échec, correction Ornith et nouveau test |
| Ingénieur sécurité | Diagnostic, limites des privilèges, refus d'action interdite |
| Rédacteur pédagogique | Guide compréhensible, document modifiable et PDF |
| Auditeur qualité | Relecture indépendante, refus d'une preuve absente |

Avant les tests Ornith, préparer et qualifier l'[image OCI des validateurs](IMAGE_VALIDATEURS_OFFLINE.md).
Le plan `python -m clawfedora.validator_acceptance` présente les seize cas
synthétiques sans Podman ; l'exécution réelle et la revue de leurs logs
restent réservées au poste Fedora.

Pour chaque rôle, constater le modèle réel, la qualité du résultat,
les outils autorisés et l'absence de repli cloud. L'ingénieur DevOps
utilise Ornith ; les six autres rôles utilisent Qwen. Vérifier que
deux tâches concurrentes ne déclenchent pas deux inférences.

Faire progresser un projet fictif de l'analyse à la livraison,
incluant les clarifications, plan et affectations, dépendances,
validation, révision et approbation humaine. Contrôler qu'une
proposition non approuvée n'est pas appliquée. Pour l'atelier de code,
utiliser un dépôt jetable, contrôler le diff, le périmètre autorisé,
les sorties de tests et le nombre borné de corrections. Ne pas
déclarer PASS uniquement sur une affirmation du modèle.

## 4. Discussions, mémoire et livrables

- Tester un long fil : historique complet conservé, contexte sélectionné,
  reprise d'un projet et isolation de deux projets. Contrôler l'affinité
  des tâches indépendantes sans changement des dépendances.
- Suivre les [canaries de streaming](STREAMING_DISCUSSIONS_NATIVES.md) :
  d'abord Mentor seul, puis sept rôles et projets. Mesurer le premier
  fragment et observer l'arrêt réel de la génération après interruption.
  Vérifier le retour au mode classique.
- Archiver explicitement un tour incertain après avoir contrôlé les
  effets possibles ; aucune relance, aucune preuve de succès inventée.
- Produire les [fichiers natifs](TELECHARGEMENTS_DISCUSSIONS.md) en JSON
  et SSE : PDF, DOCX, ODT, Markdown, code, Draw.io/SVG. Télécharger
  après redémarrage, vérifier les SHA-256, isoler deux fils et refuser
  un fichier modifié ou issu d'une réponse interrompue.

## 5. Sources et intégrations

Employer des documents synthétiques et des ressources de test GitHub
et Notion appartenant à l'opérateur. Contrôler les lectures, les
citations vers les sources originales et leur intégrité. Toute écriture
doit être explicitement approuvée ; vérifier le diff ou le contenu
attendu, puis contrôler la ressource distante. Ne pas envoyer de secrets
ni exécuter de changement sur des ressources de production.

Tester séparément la [vision locale](VISION_LOCALE_CANARY.md) sur
les images et PDF synthétiques, puis juger humainement les réponses.
Un résultat syntaxiquement valide ne certifie pas la vision.

## 6. Sauvegarde et restauration

Créer une archive privée uniquement après accord de l'opérateur,
hors génération active. La restauration doit cibler un dossier
isolé et distinct du runtime actif. Tester l'archive avec :

```bash
clawfedora-backup-verify /chemin/vers/sauvegarde.tar.gz
```

La commande restaure en copie temporaire et vérifie les empreintes
et SQLite. Pour compléter la réception, inspecter la récupération
des projets, discussions et reçus de fichiers restaurés ; vérifier
également les permissions. Ne pas publier l'archive.

## 7. Performances et stabilité

Utiliser les [profils GPU réversibles](PROFILS_GPU_EXPERIMENTAUX.md)
pour comparer les deux modèles à 8K, 16K et 32K. Chaque profil
est une expérience explicite : vérifier la configuration, mesurer
les deux modèles près de la limite, conserver les résultats privés,
puis revenir au profil de référence. Examiner la part VRAM, le
remplissage réel, les temps de chargement et les débits ; ne pas
conclure 32K intégralement sur GPU sans mesures probantes. Le
tableau Performances distingue configuration et résultat observé.

Contrôler redémarrage, services, accès au montage, veille/reprise
répétée, AV1, stabilité de la session GNOME et retour au mode
quotidien après gaming. Compléter par la
[recette visuelle native](validation/VISUAL_RECEPTION_NATIVE.md)
et l'inspection réelle des documents.

## 8. Décision humaine de réception

Pour chaque étape, consigner date, version/commit réellement testé,
résultat observé, référence de preuve privée, limite et écart éventuel.
Retester une étape après correction. Aucun rapport de ce lanceur,
aucune CI et aucune sortie de modèle ne remplacent une preuve réelle.
La décision de réception finale reste humaine, sur la machine cible.


## 9. Premier parcours métier après réception

Une fois l'atelier reçu, ouvrir le [cas de référence OpsDesk](CAS_USAGE_INFRAOPS_OPSDESK.md).
Importer volontairement le commit actuel et les seules pages Notion utiles.
Commencer par la phase de préparation du poste ou le premier exercice
non acquis ; ne pas rejouer une étape déjà prouvée. Le mentor explique,
l'apprenant agit, Ornith contrôle les propositions approuvées et l'auditeur
compare les preuves aux critères. Conserver la progression personnelle
dans Notion, le code et ses preuves techniques dans GitHub.
Aucune qualification OpsDesk ni aucun niveau d'autonomie n'est déduit
de la réception de l'atelier.

Avant le premier projet réel, exécuter également la [campagne éditoriale Premium Atlas](validation/EDITORIAL_ACCEPTANCE.md), distincte de la qualification matérielle.

## Qualification d'excellence des modèles après réception initiale

Suivre le [protocole de qualification expérimentale Fedora/B580](EXCELLENCE_NATIVE_QUALIFICATION.md) après le quick-check. La matrice candidate ne modifie ni l'installation à deux modèles ni le routage actuel.
