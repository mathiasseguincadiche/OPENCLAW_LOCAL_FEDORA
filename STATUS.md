# État du projet

Dernière mise à jour : 9 octobre 2026.

## Où en est-on

| | État |
|---|---|
| Code, scripts et configuration | Écrits et testés automatiquement |
| Configuration acceptée par le vrai OpenClaw 2026.9.8 | Vérifié à chaque modification |
| Consignes des rôles non tronquées, prompt dans le contexte | Vérifié à chaque modification |
| Installation sur le PC Fedora | **À faire** |
| Carte graphique utilisée, contexte de 32K tenu en mémoire vidéo | **À mesurer** |
| Vitesse et qualité des réponses de Qwen | **À mesurer** |
| Recherche Web des rôles (fournisseur gratuit `parallel-free`) | Configuration validée avec le vrai OpenClaw ; fonctionnement réel **à vérifier** ([Premier essai](docs/fiches/02-premier-essai.md)) |
| Cloud : filtre, budget, activation, accord par projet, pause visible | Écrits et testés avec le vrai OpenClaw et un faux fournisseur |
| Cloud avec le vrai OpenRouter (appel réel, coût réel, limite de clé) | **À faire** |
| Test de fumée du cloud sur le PC ([fiche 12](docs/fiches/12-cloud.md)) | **À faire** |
| Qualité de GLM-5.3 Flash sur les usages visés | **À mesurer** à l'usage |

Tant que les lignes « À faire » et « À mesurer » ne sont pas faites, rien n'est prouvé sur la machine ni avec le vrai fournisseur cloud. La marche à suivre est dans [Premier essai](docs/fiches/02-premier-essai.md).

## Qualité des explications en local

Rien n'est prouvé sur la justesse des explications de Qwen. Ce qui est en place : des consignes qui imposent les étiquettes observé/vérifié/proposé/non vérifié, des sources réelles uniquement, la portée exacte des contrôles ; et le cloud facultatif pour comparer ou compléter. Pistes à décider **après** le premier essai, selon les défauts réellement observés : activer le raisonnement long pour le mentor (plus lent), enrichir les consignes sur les notions où il se trompe, ou faire du mentor cloud le choix par défaut si GLM est nettement meilleur à un coût tenable. Voir [Apprendre](docs/fiches/05-apprendre.md).

## Mesures sur le PC

À remplir après `./menu.sh --action context-probe --apply`.

| Date | Contexte | Verdict | Tokens/s en sortie | Tokens/s en lecture | Mémoire vidéo |
|---|---|---|---|---|---|
| | 32 768 | | | | |

## Limites connues

- Les réponses du chat arrivent d'un bloc, sans s'afficher mot à mot.
- Une seule génération à la fois : le chat et l'atelier ne travaillent pas en même temps.
- Le chat transmet au modèle les 32 000 derniers octets de la conversation.
- Si le contexte doit être réduit à 16K, le chat ne garde plus qu'environ 500 mots d'historique. Voir [Réglages](docs/fiches/08-reglages.md).
- Les rôles n'exécutent rien : les scripts proposés sont à lancer soi-même.
- Cloud : le coût est une estimation prudente (facteur 1,3 € par dollar), pas une facture. Le relevé OpenRouter fait foi : l'enregistrer avec `cloud-reconcile`.
- Cloud : le filtre arrête les secrets, pas un contenu confidentiel qui n'en a pas l'allure. En cas de doute, rester en local.
- Cloud : le choix par défaut du chat reste local ; rien ne part tant que le modèle « · cloud » n'est pas choisi. Le coût d'une discussion cloud n'est pas rattaché à un projet.
- Cloud : la présentation illustrée (`docs/guide-utilisateur.pdf`) date d'avant le cloud et ne le mentionne pas.

## Remise en ordre d'octobre 2026

Le dépôt avait accumulé beaucoup de mécanismes sans rapport avec l'usage visé. Cette remise en ordre a :

- corrigé le contexte, qui était saturé par les consignes avant le premier message (8 192 → 32 768 tokens) ;
- fait parvenir aux rôles leurs consignes entières, alors qu'elles étaient tronquées ;
- ajouté un contrôle qui exécute le vrai OpenClaw, pour que ce type de défaut ne repasse pas inaperçu ;
- interdit au modèle l'outil qui lui permettait de mettre à jour OpenClaw ;
- retiré ce qui ne servait pas l'usage quotidien : niveaux de « qualification » L2 à L8, comparaisons de modèles, moteur llama.cpp de rechange, compilation d'un noyau, ancien suivi de coûts cloud, télémétrie (le cloud revient, borné et facultatif, avec la migration hybride ci-dessous) ;
- remplacé 27 documents par un guide et onze fiches.

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
