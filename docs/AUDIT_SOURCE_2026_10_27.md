# Audit du code source et de la maturité — 27 octobre 2026

[← Documentation](README.md) · [État](../STATUS.md) · [Essai Live USB](LIVE_USB_FEDORA45_PREQUALIFICATION.md)

## Verdict

**Le socle est cohérent et suffisamment construit pour une campagne d'essais, mais la fiabilité quotidienne de l'atelier n'est pas encore démontrée.** Des défauts de maintenance, de gestion des erreurs et de consentement cloud restent à corriger avant une réception complète.

Le contrôle Live USB existant permet la **préqualification matérielle** de Fedora 45 / GNOME 51. Il n'installe et ne teste ni OpenClaw, ni Qwen, ni Open WebUI. Un résultat favorable de ce contrôle ne vaut pas réception de l'application.

## Référence et méthode

Audit de `main` au commit `9e6322b13a9af2d84baaf51b279e81919b73f94f` (fusion de la PR #155), inventaire de 337 fichiers suivis. Revue par domaines des modules Python, scripts Bash, plugin OpenClaw, fonctions WebUI, configuration, CI et documentation. Les fichiers générés de verrou sont contrôlés par leurs validateurs et inventaires ; il ne s'agit pas d'une vérification manuelle ligne par ligne de chaque dépendance tierce.

Les constats combinent lecture du code, vérification des flux entre composants et reproductions isolées sur données synthétiques. Aucun disque utilisateur n'a été monté ou formaté, aucune installation Fedora n'a été réalisée et aucun modèle ni fournisseur cloud n'a été sollicité.

La présente modification publie l'audit et remet la documentation en cohérence. **Elle ne corrige pas les défauts fonctionnels répertoriés ci-dessous.**

## Couverture de la revue

| Domaine | Fichiers de la référence | Points examinés |
| --- | --- | --- |
| Application `src/` | 81 | 78 modules Python et interface HTML/CSS/JS : projets, chat, outils, cloud, documents, maintenance |
| Scripts `scripts/` | 36 | Installation, précontrôles, services, stockage, versions, sauvegarde, reprise et désinstallation |
| Plugins `plugins/` | 5 | Outils OpenClaw et fonctions Open WebUI ; commandes et permissions |
| Configuration `config/` | 29 | Plateforme, modèles, versions, politiques, stockage et verrous de dépendances |
| Consignes `agents/` | 25 | Sept rôles, contrats communs et limites d'action |
| Tests `tests/` | 89 | Contrats, cas de régression et lacunes révélées par les reproductions |
| Documentation `docs/` | 51 | Parcours, commandes, versions, preuves et distinction Live/installation |
| GitHub `.github/` | 7 | CI, analyses, droits des workflows et présentation ; 14 autres fichiers à la racine |

La revue couvre l'ensemble des domaines du dépôt. Elle ne certifie pas l'absence de
bugs dans chaque ligne ou composant tiers ; elle recherche surtout les défauts qui
compromettent l'objectif d'un atelier personnel fiable sur cette machine.

## Ce qui est solide

- **Architecture adaptée à l'objectif.** Deux routes d'inférence, sept spécialités,
  un moteur de projet partagé par les interfaces et une génération à la fois.
  Le cloud n'est pas un repli caché du modèle local.
- **Installation encadrée.** Précontrôle autonome avant installation des paquets,
  Python IA isolé en 3.13, versions exactes, scripts npm désactivés et artefacts
  vérifiés. Les RPM Fedora et les extras de développement ont des limites distinctes.
- **Stockage commun.** Le contrat EXT4 impose un `/data` distinct du système,
  contrôle les chemins et les liens, et fournit les préconditions des services.
  Aucun partitionnement ni formatage automatique n'est demandé au programme.
- **Pouvoirs des agents limités.** Pas de terminal libre ni d'écriture native sur
  l'hôte. Le worker vérifie les sorties prévues et collecte les fichiers ; les
  entrées et snapshots sont gardés avant/après les appels.
- **Validation humaine.** Les commandes de contrôle sont interprétées hors modèle ;
  les projets ont des étapes, confirmations, audits distincts et approbation finale.
  Le lien entre les audits et les fichiers livrés doit toutefois être renforcé (A05).
- **Surfaces locales.** Bridge/cloud sur loopback avec Host et Bearer ; écritures
  du tableau protégées par Origin, téléchargements bornés et en-têtes de protection.
  Ce modèle vise un poste personnel, pas l'isolation entre plusieurs utilisateurs
  ou processus locaux hostiles.
- **Cloud contrôlé.** Clé fournisseur côté serveur, liste blanche des paramètres,
  pas de proxy/redirection arbitraire, scan récursif du contenu sortant et journal
  budgétaire synchronisé. Deux défauts de récupération restent ouverts (A10/A11).
- **Documents et sauvegardes.** Markdown canonique, exports PDF/DOCX/ODT sans
  ressource externe, ODT borné, provenance et empreintes. Sauvegarde SQLite via
  son API, manifeste d'intégrité et restauration vers un dossier vide ; la
  cohérence de l'ensemble sauvegardé reste à garantir pendant une activité (A04).

## Défauts et priorités

**P1** : traiter avant une installation complète considérée fiable ou avant
l'activation du parcours concerné. **P2** : défaut à corriger pour la réception
quotidienne et la récupération après incident. Ces priorités expriment l'impact
dans ce projet ; elles ne sont pas toutes des vulnérabilités exploitables à distance.

| ID | Priorité | Constat | État dans cette révision |
| --- | --- | --- | --- |
| A01 | P1 | Avis de sécurité dans le verrou npm actuel | Détecté par audit du registre ; exploitabilité à examiner |
| A02 | P1 | Désinstallation sans état OpenClaw géré explicite ni arrêt confirmé | Confirmé par lecture du flux |
| A03 | P1 | Accord cloud pouvant viser le projet précédent après réponse tardive | Reproduit dans Edge, réponses API simulées |
| A04 | P2 | Sauvegarde/réparation sans exclusion du worker | Sauvegarde malgré verrou reproduite ; réparation confirmée par code |
| A05 | P2 | Fichiers modifiés après audit acceptés en livraison | Reproduit avec le moteur réel et réponses modèle simulées |
| A06 | P2 | CLI OpenClaw non trouvé par certaines commandes dans un terminal neuf | Confirmé par résolution du PATH et flux d'installation |
| A07 | P2 | Purge partielle avant échec sur les droits des modèles | Reproduit avec refus d'accès simulé |
| A08 | P2 | Timeout non traité et traitement chat restant « en cours » | Reproduit avec exception de processus simulée |
| A09 | P2 | Fichier temporaire abandonné bloquant les reprises | Reproduit avec le collecteur réel |
| A10 | P2 | Liste privée illisible traitée comme liste vide | Reproduit sans requête réseau |
| A11 | P2 | Journal budgétaire tronqué non récupéré avant le prochain append | Reproduit sur journal temporaire |
| A12 | P2 | Lecteur Office des projets autorisant les entités XML internes | Reproduit avec document synthétique bénin |
| A13 | P2 | Installation complète depuis Live non supportée, mais sans garde explicite | Lacune du précontrôle ; aucune installation Live exécutée |

### A01 — Dépendances npm : les empreintes ne remplacent pas une revue de sécurité

Le contrôle `npm audit --package-lock-only --ignore-scripts --json` sur
[le verrou](../config/npm-runtime/package-lock.json) retourne **10 entrées :
7 élevées, 3 modérées, aucune critique**. Il comprend des dépendances indirectes
et une entrée d'effet agrégé sur OpenClaw ; ce ne sont pas dix failles distinctes.
Le résultat contient 26 identifiants d'avis distincts. [Résultat brut daté](audits/2026-10-27/npm-audit.json).

| Entrée | Versions présentes dans le verrou | Niveau agrégé |
| --- | --- | --- |
| `@modelcontextprotocol/sdk` | 1.31.0 | Élevé |
| `body-parser` | 2.3.0 | Élevé |
| `brace-expansion` | 5.0.9 et 5.0.12 | Élevé sur la version affectée |
| `fast-uri` | 3.1.8 | Modéré |
| `http-cache-semantics` | 4.2.0 | Élevé |
| `ip-address` | 10.5.0 et 10.7.4 | Modéré sur la version affectée |
| `openclaw` | 2026.10.4 | Élevé par dépendances |
| `postcss-selector-parser` | 7.1.4 | Modéré |
| `undici` | 6.28.0 et 8.11.2 | Élevé |
| `zod` | 4.6.5 | Élevé |

Exemples vérifiés dans la base publique : [isolation des tâches MCP](https://github.com/advisories/GHSA-22jm-h49p-29qw),
[épuisement mémoire Zod](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) et
[erreur WebSocket Undici](https://github.com/advisories/GHSA-rfgv-xxqx-mfg5).
Les conditions d'exploitation de chaque dépendance doivent être rapprochées des
fonctions réellement activées. L'écoute locale et les outils désactivés réduisent
certaines expositions ; ils ne démontrent pas l'inaccessibilité de tous les chemins.

**À faire :** revoir les versions corrigées, régénérer les verrous et empreintes,
puis repasser les quatre contrôles OpenClaw natifs. npm propose notamment
OpenClaw 2026.10.8 ; cela reste une suggestion du registre, **pas une version
qualifiée pour cet atelier**. Aucun `npm audit fix` ni changement de version n'a
été appliqué. Ajouter un contrôle complet des dépendances existantes : Dependency
Review sur les changements d'une PR ne suffit pas pour un verrou ancien inchangé.

### A02 — Désinstallation : arrêter la bonne instance avant tout effacement

Dans [10_uninstall.sh, ligne 37](../scripts/linux/10_uninstall.sh#L37), les appels
`gateway stop/uninstall` dépendent de `command -v openclaw`, n'initialisent pas
`OPENCLAW_STATE_DIR` et ignorent leurs erreurs. Le runtime est pourtant géré sous
`/data/IA/Openclaw/state/openclaw`. La suppression des workspaces et du Python
peut ensuite continuer sans arrêt confirmé du Gateway attendu.

**À faire :** utiliser le binaire et l'environnement gérés, vérifier l'arrêt du
service concerné, puis seulement nettoyer. Tester un PATH neuf, un état OpenClaw
par défaut distinct et un échec d'arrêt. Aucun autre service réel n'a été arrêté
pendant cet audit.

### A03 — Projet actif et autorisation cloud : rejeter les réponses périmées

[dashboard.js, ligne 618](../src/clawfedora/web/dashboard.js#L618) ne vérifie pas
la séquence d'ouverture après l'attente de `/api/cloud`. Ouvrir A puis B et
recevoir les réponses dans l'ordre B puis A fait apparaître un contrôle A dans
l'éditeur B. Son bouton envoie encore `project_id=A` pour autoriser ou révoquer.

Une première reproduction utilise le vrai corps `renderCloud`, deux promesses
contrôlées et un DOM minimal. Une seconde utilise le dashboard complet dans Edge :
l’éditeur affiche « Projet Beta », la case est cochée et le bouton cliqué, mais le
POST observé contient `project_id=alpha-project`. Les API sont simulées, aucun
appel cloud réel et aucune erreur JavaScript observée. Les gardes existants de `loadProject`
et de recherche ne couvrent pas ce sous-composant.

**À faire :** vérifier l'identité et la séquence après chaque attente et avant
chaque action, afficher le nom du projet dans l'accord et couvrir aussi révocation
et erreurs tardives par un test navigateur.

### A04 — Sauvegarde et réparation : garantir une vue cohérente

[create_backup, ligne 324](../src/clawfedora/lifecycle.py#L324),
[08_backup_restore.sh](../scripts/linux/08_backup_restore.sh) et
[09_repair.sh, ligne 29](../scripts/linux/09_repair.sh#L29) ne prennent pas le
verrou global du worker. Une archive est effectivement créée alors que le verrou
est déjà détenu sur des données temporaires. SQLite reste cohérent
individuellement ; projets, état et workspaces peuvent correspondre à des instants
différents. La réparation peut modifier la configuration pendant une génération.

**À faire :** garder le verrou pendant l'opération complète et réutiliser
correctement le descripteur hérité lors d'un upgrade. Tester le refus sans
mutation pendant chat, tâche et audit. L'ancienne affirmation documentaire que
toutes ces opérations refusent une génération a été corrigée dans cette PR.

### A05 — Livraison : relier les verdicts aux octets réellement livrés

[review_project, ligne 827](../src/clawfedora/project_worker.py#L827) conserve
`snapshot_files`, mais [package_project, ligne 751](../src/clawfedora/project_engine.py#L751)
ne compare pas cet inventaire aux fichiers actuels. Après deux vrais parcours
d'audit avec réponses simulées `PASS`, modifier un livrable en état `PACKAGING`
puis appeler `project_ui.complete` permet encore d'atteindre `COMPLETE`.

La confirmation humaine et le verrou restent présents : le défaut concerne une
modification antérieure à la livraison, notamment une édition manuelle sur disque,
pas un contournement démontré de toutes les confirmations.

**À faire :** sceller l'inventaire pertinent des livrables et du plan dans les
verdicts, le vérifier aux transitions et au packaging, et invalider les audits
périmés. Tester modification, ajout et suppression ; distinguer les fichiers de
suivi légitimement créés après audit.

### A06 — Terminal neuf : retrouver le binaire installé

[06_install.sh, ligne 71](../scripts/linux/06_install.sh#L71) ajoute
`~/.openclaw/bin` au PATH de son propre processus. Aucun profil shell ne rend cet
ajout persistant. [collect_health, ligne 120](../src/clawfedora/lifecycle.py#L120)
cherche d'abord le CLI dans le PATH hérité et [09_repair.sh, ligne 39](../scripts/linux/09_repair.sh#L39)
fait de même. Une installation peut donc fonctionner via ses services mais échouer
au diagnostic ou à la réparation dans un nouveau terminal Fedora.

**À faire :** résoudre le chemin géré ou initialiser un environnement commun aux
commandes ; tester avec HOME temporaire et PATH minimal. Ne pas demander à
l'utilisateur de deviner un export permanent pour masquer le défaut.

### A07 — Purge : vérifier les droits avant la première suppression

[11_daily_profile.sh, ligne 55](../scripts/linux/11_daily_profile.sh#L55) confie les
modèles à `ollama:ollama` en mode 0750. [cleanup_managed, ligne 431](../src/clawfedora/lifecycle.py#L431)
efface d'abord des données utilisateur avant de tenter `rmtree(models)` comme
utilisateur normal. Un refus d'accès simulé dans `/tmp` déclenche `PermissionError`
alors que projets et état ont déjà été supprimés.

**À faire :** contrôler toutes les permissions avant mutation, arrêter Ollama,
définir une suppression privilégiée strictement bornée et décrire exactement ce
qui reste. Les sources, sauvegardes et certaines données runtime ne sont pas une
purge totale du répertoire. La reproduction n'a pas créé de compte Ollama ni
modifié les droits du vrai disque.

### A08 — Délais dépassés : terminer les traitements en erreur visible

[chat_run.py, ligne 117](../src/clawfedora/chat_run.py#L117) ne prend pas en charge
`subprocess.TimeoutExpired`, que le runner peut émettre. Injecter cette exception
termine le thread mais laisse `chat-jobs` à `running` et `!etat` annonce encore
« en cours », même avec verrou libre. Des traitements du dashboard et du bridge
présentent la même lacune ; le worker de tâches couvre déjà une partie des timeouts.

**À faire :** traiter explicitement les délais dépassés, enregistrer un état
terminal et reconnaître les travaux interrompus après redémarrage. Tester chat,
proposition, audit et reprise, en vérifiant l'arrêt effectif de l'inférence avant
de libérer un verrou ; ne pas confondre délai HTTP et arrêt réel du modèle.

### A09 — Collecte interrompue : récupérer le staging

[_collect, ligne 414](../src/clawfedora/project_worker.py#L414) crée un nom fixe
`*.worker-tmp` avec ouverture exclusive. Après une coupure avant `replace`, ce
fichier peut subsister. Deux appels successifs du vrai collecteur avec un temporaire
partiel précréé échouent tous deux avec `FileExistsError`.

**À faire :** staging par tentative, nettoyage contrôlé et promotion récupérable ;
tester une coupure après création et entre deux fichiers. Préserver les anciennes
sorties et ne pas consommer des tentatives sans signaler la cause.

### A10 — Confidentialité : ne pas perdre silencieusement une règle configurée

[PrivacyFilter._terms, ligne 153](../src/clawfedora/cloud_privacy.py#L153) transforme
un `OSError` en liste vide. Une liste contenant un nom interne synthétique le bloque ;
la remplacer par un répertoire supprime silencieusement cette protection au scan
suivant. Les détecteurs génériques de secrets continuent à fonctionner.

**À faire :** distinguer une liste optionnelle absente d'une liste configurée
illisible ou non régulière, refuser le cloud dans le second cas et tester la
relecture après remplacement/erreur. Aucun contenu n'a été envoyé au fournisseur.

### A11 — Budget : réparer une écriture tronquée avant le prochain ajout

[cloud_budget.py, lignes 103 et 117](../src/clawfedora/cloud_budget.py#L103) ignore
un dernier fragment JSON incomplet à la lecture, puis ajoute la réservation suivante
directement derrière. Le `summary()` suivant échoue `BudgetRefused` : un crash
peut laisser démarrer un appel de reprise avant de bloquer les suivants.

**À faire :** récupérer la fin de journal sous verrou avant tout append, conserver
les réservations complètes et tester plusieurs cycles après coupure. Le test
existant ne relit pas entre le nouvel ajout et une autre corruption. Ce constat
prouve un défaut de récupération ; il ne prouve pas une dépense illimitée.

### A12 — Import Office : appliquer le même durcissement XML aux projets

[_office_extract, ligne 230](../src/clawfedora/project_intake.py#L230) utilise le
lecteur XML standard, alors que chat et ODT emploient `defusedxml`. Un document
DOCX synthétique avec une entité interne bénigne est accepté et son texte développé.
Le plafond de texte extrait intervient après le parsing.

**À faire :** réutiliser le lecteur défensif déjà présent, refuser DTD/entités et
borner les entrées XML. Conserver les limites ZIP. Expat possède déjà des protections
d'amplification : aucune exfiltration, lecture externe, macro ou exécution de code
n'a été démontrée par cette reproduction.

### A13 — Live USB : refuser explicitement un parcours non supporté

Le [précontrôle d'installation](../scripts/validation/preinstall_host.py#L44)
contrôle la plateforme et `/data`, mais pas les marqueurs `rd.live.image` ou
`root=live:`. Une session Live finale satisfaisant les autres critères pourrait
donc écrire un runtime persistant sur `/data`, avec paquets, comptes et services
restant dans un système temporaire.

**À faire :** refuser ce mode dans l'installateur tant qu'un vrai parcours Live
persistant n'est pas conçu et qualifié. Le [script de préqualification Live](../scripts/linux/16_live_usb_preflight.sh)
reste adapté à l'observation sans installation. Aucun contournement du précontrôle
ni essai d'installation Live n'a été réalisé pendant cet audit.

## Vérifications exécutées et limites des preuves

| Vérification | Résultat | Ce que cela ne prouve pas |
| --- | --- | --- |
| Suite locale Python 3.13.17, après adaptation documentaire | **1 105 réussis**, 37 avertissements, couverture **85,77 %** | Qualité des réponses ou réception Fedora |
| Ruff, mypy, validation des contrats, syntaxe Bash, ShellCheck | Réussis ; 78 modules contrôlés par mypy | Absence de défaut logique ou de risque tiers |
| Vérification des verrous | 23 paquets Python, 2 build, 21 voix ; 413 npm hachés et 150 embarqués | Innocuité des versions ainsi verrouillées |
| CI après fusion #155 | [Dix jobs réussis](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/40119337966), quality : 1 104 tests, 85,80 % | Couverture des nouveaux cas de panne découverts |
| CodeQL après fusion #155 | [Réussi](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/40119338118) | Certification de sécurité ou d'exploitation |
| Avis Python de production | [23 versions, aucun avis connu retourné](audits/2026-10-27/python-audit.json) via `pip-audit --disable-pip --no-deps` | Paquets voix/build, RPM, image WebUI ou absence de faille inconnue |
| Avis npm | [10 entrées signalées](audits/2026-10-27/npm-audit.json), 7 élevées/3 modérées | Exploitabilité démontrée dans cette configuration |
| README rendu en navigateur | Grand écran 1280 et mobile 390 px, sans débordement horizontal global | Rendu exact de GitHub ou fonctionnement de WebUI |

La première tentative locale de tests ne pouvait pas créer les sockets loopback
dans l'environnement restreint de l'audit. Elle n'a pas servi de résultat logiciel :
la suite complète a été relancée avec cet accès local et a réussi. Les avertissements
restants comprennent des connexions SQLite non fermées dans les tests ; les traiter
en maintenance sans les confondre avec un échec de réception sur le PC.

Les scans de dépendances sont des instantanés du **27 octobre 2026**. Aucun scan
de l'image WebUI effectivement tirée, des RPM du futur poste ou de toutes les
options d'OpenClaw n'a été effectué. Les mises à jour de versions doivent conserver
les essais natifs et les verrous ; un résultat vert antérieur n'est pas réutilisable
comme preuve de leur compatibilité après modification.

## Ce qui manque, ce qu'il faut ajouter, ce qu'il faut retirer

### Ajouter en priorité

1. Les corrections A01–A13 avec des régressions qui reproduisent les scénarios,
   particulièrement le changement rapide de projet, l'arrêt raté d'un service,
   les timeouts, les coupures d'écriture et la modification après audit.
2. Une réception de bout en bout sur une installation de test : chat local,
   fichiers réels, petit projet jusqu'à livraison, pause/reprise, redémarrage,
   sauvegarde puis restauration et reprise des services sur une copie.
3. Une revue périodique des avis sur l'ensemble des dépendances déjà présentes,
   et une qualification du fournisseur avant tout essai cloud : dossier public,
   accord explicite, limite de clé et facture/coût observés.
4. Une visibilité sur l'espace pris par les snapshots de tâches et d'audits, puis
   une politique de rétention explicite ; ne pas supprimer les preuves au hasard.

### Garder facultatif ou différer

- **Streaming et vrai arrêt :** utiles pour le confort d'un chat, mais le canary
  local Mentor n'établit pas l'arrêt du modèle. Le bouton Stop actuel coupe
  l'affichage ; la pause projet est coopérative. Réception séparée avant extension.
- **32K :** configuration prévue, capacité GPU à mesurer. Le contrôle court ne
  certifie pas le contexte proche de sa limite.
- **Voix, vision et file persistante :** les laisser derrière une réception
  volontaire ; ne pas multiplier services, agents ou modèles avant la stabilité.
- **Qualité pédagogique :** mesurer des conversations réelles, avec la grille
  existante, plutôt que déduire une qualité du nombre de tests.

### Retirer ou simplifier

- Les recettes d'installation dupliquées dans le README et le guide de découverte :
  leur déplacement vers le guide opérationnel a été fait dans cette PR.
- Les affirmations de refus automatique de toute maintenance et de purge complète :
  corrigées dans la documentation, sans prétendre corriger le code.
- Les anciennes versions et anciens chemins dans les pages actives : version SSE,
  métadonnées `/data` et référence de CI actualisées. Les archives gardent leurs URLs.
- Les petits libellés trompeurs du code, par exemple `6 managed` alors que sept
  workspaces sont vérifiés (`lifecycle.py:158`), restent à nettoyer dans un correctif.
  Ce point ne retire pas un agent et ne justifie pas à lui seul un blocage.
  `chat_flow.py:40–41` affiche aussi encore « le chat le pilotera plus tard » pour
  un plan approuvé, alors que `!lancer` existe ; ce texte atteint les prochaines
  étapes de l’interface et doit être actualisé.

Aucun motif trouvé pour supprimer ODT, les sept rôles, les contrôles humains ou
le stockage dédié. Le projet a déjà une offre fonctionnelle large ; la priorité
est sa fiabilité et sa qualification, pas l'ajout d'un troisième moteur.

## Campagne matérielle et décision de maturité

| Étape | Ce qu'elle établit | Verdict possible |
| --- | --- | --- |
| Live USB Fedora 45 / GNOME 51 | UEFI, B580/xe, bureau, affichage, réseau, audio et premier cycle veille | Matériel préqualifié, installation non autorisée par le script |
| Installation de test, après corrections | Paquets, droits, montage, services persistants, compte WebUI, réponse locale | Premier usage applicatif reçu |
| Projet et récupération | Livraison reliée aux audits, reprise après erreur, restauration cohérente | Candidat à l'usage quotidien |
| Cloud, si souhaité | Accord sur le bon projet, refus secrets, coût et limite fournisseur | Route hybride reçue sur un exemple borné |

**Situation de Fedora vérifiée le 27 octobre :** la publication finale a été
refusée le 22 octobre et la cible reportée au 3 novembre, sous réserve de décision
ultérieure. Le [compte rendu officiel](https://meetbot.fedoraproject.org/meeting_matrix_fedoraproject-org/2026-10-22/f45-final-go-no-go-meeting.2026-10-22-17.00.html)
fait foi ; ne pas prendre le seul numéro 45 dans `os-release` comme preuve d'une
ISO finale officiellement publiée.

**Décision :** accord pour préparer l'observation matérielle Live en respectant
le protocole ; pas encore de déclaration « prêt et fiable au quotidien » pour
l'atelier complet. Les corrections identifiées puis les preuves réelles décideront
de cette maturité. Pour essayer l'application avant de remplacer le système
actuel, une installation Fedora sur un support dédié serait une campagne distincte
à préparer ; aucune recette Live éphémère complète n'est actuellement qualifiée.
