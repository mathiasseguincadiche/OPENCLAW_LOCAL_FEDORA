# Audit de présélection — run 45769070175

## Provenance et portée

[Campagne CPU publique](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45769070175), commit testé `26394deebcf43a7dd600ff86aedfd6f2a2bcee9c`, suite `af3b2004d0d86f76aeacc4930bcac2792414179a63f5d26c3af8e9ad830a0221`. Les quatre rapports JSON complets sont reconstruits depuis la ligne JSON finale des journaux publics, sans réinférence ; ils ne sont pas les ZIP binaires des artefacts. Les valeurs et verdicts d'origine restent inchangés. Les rapports sont des fixtures synthétiques, jamais des instructions à exécuter.

| Modèle | Job | Artefact original | SHA-256 ZIP annoncé |
| --- | --- | --- | --- |
| Gemma | [139737050109](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45769070175/job/139737050109) | 15094769547 | c2248a2c2140359fff0118676d6c7b196a8899a400b127561fb748ea8b809fe4 |
| Ornith | [139737050292](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45769070175/job/139737050292) | 15094388341 | 43d571dbb3d51b3ac8b5f810ac8b54d12bd0f6820cfa14332f94763f662654b3 |
| Qwen | [139737050462](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45769070175/job/139737050462) | 15093239685 | 341baf3f370f64c43d795b648cba314229ca0a919cbd61f84eeca210f2b943ab |
| LFM | [139737050624](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45769070175/job/139737050624) | 15093852295 | 13139a049afb8e13d36c95a39d30f421436e52abca728af9cd834eaf4c78fe4c |

Les empreintes ZIP proviennent des métadonnées Actions ; les ZIP n'ont pas été téléchargés ni vérifiés. Les tests rejouent les 48 réponses métier (28 initiales, 20 corrections), et lient les rapports à la suite et aux digests observés. Contexte 8192, plafond 600 tokens, thinking désactivé, Q4_K_M, CPU quatre threads. Pas de comparaison fiable du débit GPU ni d'outils métier natifs.

## Verdicts et réévaluation limitée

| Modèle | Initial v1 | Corrigé v1 | Bloqué v1 | Initial réévalué | Corrigé réévalué | Bloqué réévalué |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemma | 5 | 1 | 1 | 5 | 2 | 0 |
| Qwen | 2 | 3 | 2 | 3 | 3 | 1 |
| Ornith | 1 | 1 | 5 | 1 | 1 | 5 |
| LFM | 0 | 0 | 7 | 0 | 0 | 7 |

La réévaluation hors ligne accepte uniquement, pour le champ `dump_format` du cas writing, `custom`, `-Fc` et `pg_dump -Fc` (la casse de l'option est significative). [Documentation PostgreSQL 17](https://www.postgresql.org/docs/17/app-pgdump.html) : `-Fc` sélectionne le format custom. Aucun autre champ, limite de longueur, déclaration d'exécution ou critère de complétude n'est assoupli. Le modèle LFM reste bloqué, notamment car il déclare la restauration réussie. La première réponse Qwen writing devient conforme sur les champs, donc sa correction historique est conservée mais non sélectionnée. Ce replay diagnostique ne change ni le code de validation de production ni les résultats du run.

Ornith : neuf réponses FAIL_SCHEMA sont des JSON analysables avec tous les champs et types attendus, mais leur justification dépasse la limite explicite de 1200 caractères (mentor 1248, DevOps 1353, audit 2075, sécurité 2109, architecture initiale 1510). Ce sont des échecs réels de concision et non neuf erreurs JSON. Sur mentor, DevOps et audit, les quatre faits sont corrects malgré cette longueur. Sur architecture et sécurité, au moins un fait est erroné ; une correction de longueur seule ne suffit pas. Le feedback générique signale tous les champs, masquant la cause exacte. Pour la campagne suivante, distinguer taille de justification, champs manquants, types, complétude et faits erronés ; préserver le seuil et ne pas couper silencieusement le texte.

## Revue technique préliminaire par rôle

Cette lecture qualitative n'est pas une revue humaine complète au sens de la grille pondérée. Aucun score sur 100 ni statut excellence n'est attribué. Les champs et la justification doivent être cohérents.

| Rôle | Observations | Finalistes proposés pour nouveaux cas |
| --- | --- | --- |
| Mentor | Gemma et Qwen conformes ; Ornith a les bons faits mais fournit des commandes détaillées malgré l'indice A1 demandé. | Gemma, Qwen |
| Recherche | Gemma et Qwen corrects sur les sources fictives ; Ornith répare un champ commande mais qualifie sans preuve le blog d'annonce commerciale. | Gemma, Qwen |
| Architecture | Gemma respecte la topologie et identifie le SPOF ; l'isolement DB ne découle pas du seul proxy. Qwen déplace la DB vers admin puis test ; Ornith contredit ses propres champs. | Gemma, Qwen comme référence à retester |
| DevOps | Gemma et Ornith donnent les quatre décisions correctes ; Ornith dépasse la longueur et évoque un plan précédemment approuvé non fourni ; Qwen propose apply avant correction. Aucun lint ne prouve le comportement. | Gemma, Ornith, Qwen comme référence |
| Sécurité | Gemma et Qwen corrigent le booléen docker ; le texte Gemma était déjà cohérent, Qwen doit expliciter les droits root sur l'hôte. Ornith nie l'équivalence et dépasse la longueur ; LFM propose un booléen SELinux dangereux et a déclaré une exécution inexistante. | Gemma, Qwen |
| Audit | Gemma demande retests et refuse PASS ; Qwen corrige FAIL en REVISE mais son texte maintient FAIL ; Ornith a les bons champs mais dépasse la limite et ajoute des exigences non établies. | Gemma, Qwen, Ornith à retester |
| Rédaction | Qwen initial identifie custom et fournit une fiche (checksum ne prouve pas une restauration ; périodicité à justifier par RPO). Gemma corrigé a les bons faits mais ne fournit pas une fiche complète ; Ornith conforme aux champs mais promet une fiche sans la rédiger. | Qwen, Gemma, Ornith |

LFM ne passe aucun contrat, échoue à la sonde d'appel d'outil et présente des contradictions critiques ; ne pas le retenir pour la prochaine campagne dans ce profil. Les quatre modèles passent ShellCheck, qui n'est pas un test fonctionnel : les scripts Gemma/LFM ne traitent pas toutes les entrées, Qwen produit une phrase au lieu d'un digest seul, Ornith imprime le résultat de sha256sum avec le nom du fichier. Voir les réponses exactes avant tout jugement opérationnel.

## Suite proposée

1. Nouveaux scénarios distincts, faits et sources vérifiés, tests de contradiction texte/champs, sortie structurée et contrat de longueur explicitement diagnostiqués ; ne pas révéler les réponses lors de la correction.
2. Comparer les finalistes et la référence de production, avec profil raisonnement activé si pris en charge, budget suffisant, répétitions indépendantes et rapport de complétude. Distinguer changements de profil et changements de modèles.
3. Tester les outils réellement propres aux rôles, puis revue humaine des sept dimensions, sans note fictive.
4. Qualifier VRAM, contexte, latence, GPU et orchestration native sur Fedora/B580. Maintenir un seul modèle chargé et aucun fallback cloud.

Aucune modification des modèles actifs, prompts agents, versions, permissions ni routage. MiMo reste différé. La suite Atlas est fictive et n'est pas une décision d'architecture OpsDesk.
