# État du projet hybride Qwen + DeepSeek

Dernière mise à jour documentaire : 14 octobre 2026 (socle neuf sous versions stables).

## Où en est-on

| | État |
|---|---|
| Code, scripts et configuration | Écrits et testés automatiquement |
| Configuration acceptée par le vrai OpenClaw 2026.10.3 | Vérifié à chaque modification |
| Consignes des rôles non tronquées, prompt dans le contexte | Vérifié à chaque modification |
| Installation sur le PC Fedora | **À faire** |
| Carte graphique utilisée, contexte de 32K tenu en mémoire vidéo | **À mesurer** |
| Vitesse et qualité des réponses de Qwen | **À mesurer** |
| Recherche Web des rôles (fournisseur gratuit `parallel-free`) | Configuration validée avec le vrai OpenClaw ; fonctionnement réel **à vérifier** ([Premier essai](docs/fiches/02-premier-essai.md)) |
| Cloud : filtre, budget, activation, accord par projet, pause visible | Écrits et testés avec le vrai OpenClaw et un faux fournisseur |
| Cloud avec le vrai OpenRouter (appel réel, coût réel, limite de clé) | **À faire** |
| Test de fumée du cloud sur le PC ([fiche 12](docs/fiches/12-cloud.md)) | **À faire** |
| Qualité de DeepSeek V4.1 Flash sur les usages visés | **À mesurer** à l'usage |
| Open WebUI : conduite complète des projets, uploads, pratique guidée | **Implémenté et couvert par tests automatiques** ; cycle de vie corrigé (arrêt des quatre services) |
| Voix locale : Whisper CPU/int8 + TTS local | **Implémenté ; essai micro/latence à faire sur Fedora** |

Tant que les lignes « À faire » et « À mesurer » ne sont pas faites, rien n'est prouvé sur la machine ni avec le vrai fournisseur cloud. La marche à suivre est dans [Premier essai](docs/fiches/02-premier-essai.md).

## Stabilisation du code du 14 octobre 2026

Cinq correctifs ont été **fusionnés après CI, CodeQL et Dependency Review verts**
([#110](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/110) à
[#114](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/114)) :

- bootstrap Python sans mise à niveau non bornée, `pip check` et contrôle de cohérence npm ;
- réseau Podman du canary Open WebUI 0.12 unique par exécution, sans migration de production ;
- passerelle OpenRouter sans redirections ni proxys implicites, plafonds inchangés ;
- comparaison **humaine** locale/cloud des sept rôles, sans appel modèle ni classement automatique ;
- précontrôle système sensible aux unités désactivées au démarrage, sondes locales sans redirection.

**Ces résultats sont des preuves de tests du code, pas des essais sur le PC cible**.
Les dépendances transitives ne sont pas entièrement verrouillées ; Open WebUI
reste en `v0.11.4` jusqu'à la réception navigateur/SQLite ; l'exactitude des
profils OpenRouter et de la facturation reste à mesurer sur un compte réel.
Fedora 45 est encore une cible de preview de contrats, **non un hôte installable
validé par le bootstrap**.

## Lire et comprendre le projet

Le [README](README.md) présente le projet comme **hybride**, et [la stratégie Qwen + DeepSeek](docs/ARCHITECTURE_HYBRIDE.md) explique quand et pourquoi utiliser chaque moteur ; le [guide](docs/GUIDE.md) permet de découvrir l'atelier dans l'ordre. La fiche [Rôles et outils](docs/fiches/07-roles-et-outils.md) distingue précisément les droits des sept agents ; [Comment ça marche](docs/fiches/11-comment-ca-marche.md) explique les ports, flux et limites de preuve. Le [parcours DevOps](docs/EXEMPLE_PARCOURS_DEVOPS.md) est **fictif et pédagogique**, pas un test effectué.

Les deux diagrammes de `docs/diagrams/` sont des **représentations logiques du code**, non des preuves d'exécution physique. Les critères et mesures manquants restent ceux décrits dans ce document.

## Profils de raisonnement DeepSeek

Le code propose trois **profils globaux** de raisonnement DeepSeek,
`rapide` (`low`/4K), `equilibre` (`medium`/8K) et `approfondi`
(`xhigh`/32K, valeur historique par défaut). Seul l'opérateur
peut enregistrer un changement via `cloud-set-profile --value ... --apply`.
Le fichier est privé, le verrou worker interdit de changer le profil
durant une génération normale et la passerelle plafonne la réponse
**avant** la réservation du budget. Les contrôles du consentement,
de la confidentialité et de prix ne sont pas modifiés.

**À qualifier en dernier :** bonne application de `reasoning.effort`
par le véritable hébergeur DeepSeek sous OpenRouter, facture, latence,
qualité réelle des sorties et impact sur les itérations. Le réglage
reste global et manuel, jamais une sélection automatique par tâche.

## Choix de modèle assisté

La commande `!modele` et le raccourci Open WebUI **Quel modèle choisir ?**
fournissent un **conseil déterministe local** selon des catégories métier.
Ils ne consultent aucune conversation, ne modifient pas le modèle sélectionné,
n'envoient rien au cloud et **ne valident pas** la confidentialité des sources.
L'interface réelle et la pertinence des conseils restent à vérifier lors des
essais finaux. La sélection automatique par tâche n'est toujours pas implémentée.

## Qualification de l'efficacité du système hybride

**Objectif technique :** Qwen local pour les tâches courantes et privées, DeepSeek cloud pour les dossiers publics difficiles et les analyses multi-fichiers. Les sept rôles partagent les mêmes outils ; la route est choisie explicitement et le consentement cloud d'un projet s'applique au **projet**.

**Ce qui est vérifié :** la présence des deux routes dans les politiques, les filtres et budgets simulés, les règles de blocage et l'absence de bascule locale → cloud cachée.

**Ce qui n'est pas vérifié :** la qualité comparative Qwen/DeepSeek, l'amélioration réelle du temps de travail, le coût facturé et la sélection du fournisseur sur le véritable PC. Le routage automatique par difficulté/tâche n'est **pas implémenté**.

→ [Pourquoi l'architecture est hybride](docs/ARCHITECTURE_HYBRIDE.md) · [Comment comparer les modèles](docs/DECISION_MODELE.md).

## Qualité des explications en local

Rien n'est encore mesuré sur ta machine. Les résultats publics de DeepSeek V4.1 Flash sont très solides sur les tâches agentiques, le code et l'usage d'outils, mais ils ne constituent pas un test direct de pédagogie face à Qwen 3.5 9B. La règle reste donc simple : Qwen local par défaut pour le quotidien et le confidentiel ; DeepSeek cloud, sur demande, pour les questions publiques complexes, les longues analyses et les tâches où un modèle plus puissant apporte une vraie valeur. La comparaison sur tes propres questions décidera ensuite s'il faut donner plus de place au mentor cloud. Voir [Quel modèle pour expliquer](docs/DECISION_MODELE.md) et [Apprendre](docs/fiches/05-apprendre.md).

## Mesures sur le PC

À remplir après `./menu.sh --action context-probe --apply`.

| Date | Contexte | Verdict | Tokens/s en sortie | Tokens/s en lecture | Mémoire vidéo |
|---|---|---|---|---|---|
| | 32 768 | | | | |

## Vérification des preuves de CI publiques

La commande `clawfedora-ci-proof` vérifie en lecture seule le **statut global**
d'un pipeline public GitHub/GitLab via l'API officielle, après comparaison
de l'identifiant d'exécution et du SHA du commit. L'option `--jobs` fournit
désormais une liste bornée des métadonnées de jobs publics rattachés au pipeline ;
toute pagination non vérifiable est refusée. Elle **ne télécharge pas**
de journaux et ne valide pas les artefacts, les déploiements ou les backups.
Sa logique est testée sur de faux API ; les appels réels sur Fedora et les
connecteurs privés restent à qualifier. [Guide](docs/PREUVES_CI_GITHUB_GITLAB.md).

## Exécuteur de validation DevOps

**Ce validateur est totalement facultatif, et non une dépendance du système IA natif Fedora.**
Le code du [validateur DevOps isolé](docs/LABORATOIRE_DEVOPS.md) fournit
une CLI séparée des agents, avec exécution Podman contrôlée et
approbation `--apply`. Si l'utilisateur souhaite s'en servir, il reste
à qualifier une image OCI de validateurs **sans imposer Rocky Linux**
et les essais Podman réels. Aucun agent ne lance Terraform, Ansible
ou la CI sur l'hôte.

## Évaluation des agents, préparation

Le dépôt comporte une **suite synthétique fixe de sept scénarios métier**, une CLI `clawfedora-evals` et un format de revue humaine. Cela vérifie la structure du plan et la complétude des notes, **pas** la qualité réelle de Qwen ou DeepSeek. Les résultats comparatifs seront établis seulement lors de la qualification finale. [Mode d'emploi](docs/EVALUATION_AGENTS.md) · [Programme global](docs/PROGRAMME_AMELIORATION_2026.md).

## Documents de conversation et exports vérifiables

Le chat **local sans projet** peut désormais produire des aperçus de petits PDF
contenant du texte et de fichiers Office (DOCX, PPTX, XLSX), sous limites de
taille et de contexte. Sans activation, les images PNG/JPEG/WebP ne fournissent que leurs
**métadonnées vérifiées**. La nouvelle voie de **vision locale Qwen** est
strictement canary (marqueur privé 0600) et ne touche jamais OpenRouter ;
les images et PDF scannés courts peuvent alors être décrits par Qwen
après prévalidation et verrou worker. La précision visuelle sur B580 n'est
**pas encore qualifiée**. Les PDF
scannés sans texte, les archives et les usages cloud avec fichiers restent
refusés dans cette voie. Tests simulés intégrés (PR #97), rendu réel Open WebUI
à vérifier sur Fedora.

La commande humaine `clawfedora-doc-bundle` assemble jusqu'à 16 sections
Markdown relues en source éditable, PDF, DOCX et manifeste SHA-256, sans
écrasement ni exécution d'agent (PR #93). L'outil Draw.io accepte désormais
un fichier éditable de **1 à 8 vues indépendantes** (PR #98), dont seule la
première est représentée dans le SVG/Mermaid d'aperçu. Les qualités visuelles
et pédagogiques des exports doivent encore être inspectées manuellement.

## Pilotage visuel des projets Open WebUI

Le plugin Action propose **six boutons en lecture seule**, dont **Voir les sources**, **huit
boutons de transition** (analyse, plan, lancer, pause, reprise, audit,
relecture, préparation de livraison), plus trois formulaires : **Créer
un projet**, **Répondre à une précision** et **Demander une révision**.
Une action mutante exige la confirmation du navigateur ; la création,
la révision et la livraison conservent ensuite la phrase d'approbation
indépendante, émise par le pont. Les tests couvrent des dialogues simulés,
les appels du pont, l'absence d'historique transmis par les boutons et
les cas d'annulation. **Le rendu sur le véritable Open WebUI et la
fiabilité de ses dialogues restent non qualifiés sur Fedora.**
Le formulaire de révision ne change aucun livrable au premier clic :
le moteur calcule les tâches affectées et émet un code distinct à saisir
dans le chat. La soumission guidée de fichiers reste disponible par
commande, sans formulaire dédié.

## Streaming SSE natif — PR #89 et #90

Le streaming est **raccordé au pont Open WebUI dans le code** pour le chat
simple du Mentor Qwen local ; il est **désactivé par défaut**. L'activation
canary volontaire exige un marqueur privé `0600`, la prévalidation
OpenClaw/Ollama/modèle/rôles, un Gateway en boucle locale et son jeton
opérateur privé côté serveur. Les commandes, projets, autres rôles,
pièces jointes et appels DeepSeek conservent leur chemin habituel. La
révocation canary force `enabled=false` dans le patch du Gateway. Les PR
[#89](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/89)
et [#90](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/90)
sont fusionnées, avec CI/CodeQL verts. **Aucun flux réel n'a encore été
qualifié sur Fedora/Open WebUI** : ne pas confondre canary disponible,
activation et validation physique. [Activation et rollback](docs/STREAMING_SSE_PREPARATION.md).

## Séparation entre l'atelier IA Fedora et une VM de formation

**Le projet IA fonctionne sur Fedora :** OpenClaw et ses sept rôles,
Ollama/Qwen, la passerelle DeepSeek, le moteur de projets et les données
sont hébergés sur Fedora ; Open WebUI utilise Podman rootless
sur ce même hôte. **Rocky Linux n'est ni un système hôte requis,
ni une VM nécessaire, ni une dépendance de lancement de l'atelier.**
Une VM Rocky de formation, si utilisée, appartient à un parcours
DevOps externe au projet IA. Les priorités du dépôt sont désormais
**canary et qualification du streaming Open WebUI**, cohérence des documents,
puis **pilotage visuel des projets**.

## Limites connues

- Par défaut, les réponses du chat arrivent d'un bloc via le CLI ; le streaming SSE natif est raccordé en canary privé et reste à qualifier sur Fedora.
- Une seule génération à la fois : le chat et l'atelier ne travaillent pas en même temps.
- Le chat local transmet les 32 000 derniers octets de la conversation ; la route DeepSeek peut transmettre jusqu'à environ 3 Mio d'historique dans la limite du contexte cloud de 1 048 576 tokens.
- Si le contexte doit être réduit à 16K, le chat ne garde plus qu'environ 500 mots d'historique. Voir [Réglages](docs/fiches/08-reglages.md).
- Les rôles n'exécutent rien : les scripts proposés sont à lancer soi-même.
- Cloud : le coût est une estimation prudente (facteur 1,3 € par dollar), pas une facture. Le relevé OpenRouter fait foi : l'enregistrer avec `cloud-reconcile`.
- Cloud : le filtre arrête les secrets, pas un contenu confidentiel qui n'en a pas l'allure. En cas de doute, rester en local.
- Cloud : le choix par défaut du chat reste local ; rien ne part tant que le modèle « · cloud » n'est pas choisi. Le coût d'une discussion cloud n'est pas rattaché à un projet.
- Les lots 9 à 15 d'[Open WebUI](docs/PLAN_INTEGRATION_WEBUI.md) sont implémentés : lecture/cadrage, exécution, audits, pratique guidée, livraison, uploads, import de secours et voix locale. Le rendu réel de l'interface, le micro, la latence vocale et les préfixes `!` / `/` restent à vérifier au test de fumée sur le PC.

## Remise en ordre d'octobre 2026

Le dépôt avait accumulé beaucoup de mécanismes sans rapport avec l'usage visé. Cette remise en ordre a :

- corrigé le contexte, qui était saturé par les consignes avant le premier message (8 192 → 32 768 tokens) ;
- fait parvenir aux rôles leurs consignes entières, alors qu'elles étaient tronquées ;
- ajouté un contrôle qui exécute le vrai OpenClaw, pour que ce type de défaut ne repasse pas inaperçu ;
- interdit au modèle l'outil qui lui permettait de mettre à jour OpenClaw ;
- retiré ce qui ne servait pas l'usage quotidien : niveaux de « qualification » L2 à L8, comparaisons de modèles, moteur llama.cpp de rechange, compilation d'un noyau, ancien suivi de coûts cloud, télémétrie (le cloud revient, borné et facultatif, avec la migration hybride ci-dessous) ;
- remplacé l'ancienne documentation dispersée par un guide et des fiches thématiques (le parcours de découverte a ensuite été enrichi).

Le dépôt est passé d'environ 15 500 à 9 200 lignes de Python. Tout ce qui a été retiré reste dans l'historique Git.

## Migration hybride d'octobre 2026

Le plan est dans [PLAN_MIGRATION_HYBRIDE.md](docs/PLAN_MIGRATION_HYBRIDE.md) et la conception dans [PASSERELLE_CLOUD.md](docs/PASSERELLE_CLOUD.md). Une branche et une pull request par lot, sans fusion automatique :

| Lot | Contenu |
|---|---|
| 1 | Correctif de l'attente des 8 outils + plan |
| 2 | Consignes des rôles V2.3, contrôles de taille et de contrat |
| 3 | Fondation de la passerelle cloud (désactivée par défaut) |
| 4 | Exécuteur avec route cloud explicite, sans repli du local vers le cloud |
| 5 | Passerelle locale, filtre de confidentialité, modes Apprendre et Travail |
| 6 | Budget de 25 € réels, journal de tous les appels, activation contrôlée |
| 7 | Atelier : accord par projet, pause visible, modèle et coût affichés |
| 8 | Documentation, et sauvegardes qui n'emportent plus la clé du fournisseur |

Hors périmètre pour l'instant, chacun sur nouvel accord : validateurs comme outils d'agent, contrôle des citations, Mistral Large 4 avec sous-plafond, registre de compétences, laboratoire d'exécution.
