# État du projet

Dernière mise à jour : 7 octobre 2026.

## Où en est-on

| | État |
|---|---|
| Code, scripts et configuration | Écrits et testés automatiquement |
| Configuration acceptée par le vrai OpenClaw 2026.9.8 | Vérifié à chaque modification |
| Consignes des rôles non tronquées, prompt dans le contexte | Vérifié à chaque modification |
| Installation sur le PC Fedora | **À faire** |
| Carte graphique utilisée, contexte de 32K tenu en mémoire vidéo | **À mesurer** |
| Vitesse et qualité des réponses de Qwen | **À mesurer** |

Tant que les trois dernières lignes ne sont pas faites, rien n'est prouvé sur la machine. La marche à suivre est dans [Premier essai](docs/fiches/02-premier-essai.md).

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

## Remise en ordre d'octobre 2026

Le dépôt avait accumulé beaucoup de mécanismes sans rapport avec l'usage visé. Cette remise en ordre a :

- corrigé le contexte, qui était saturé par les consignes avant le premier message (8 192 → 32 768 tokens) ;
- fait parvenir aux rôles leurs consignes entières, alors qu'elles étaient tronquées ;
- ajouté un contrôle qui exécute le vrai OpenClaw, pour que ce type de défaut ne repasse pas inaperçu ;
- interdit au modèle l'outil qui lui permettait de mettre à jour OpenClaw ;
- retiré ce qui ne servait pas l'usage quotidien : niveaux de « qualification » L2 à L8, comparaisons de modèles, moteur llama.cpp de rechange, compilation d'un noyau, suivi de coûts cloud, télémétrie ;
- remplacé 27 documents par un guide et onze fiches.

Le dépôt est passé d'environ 15 500 à 9 200 lignes de Python. Tout ce qui a été retiré reste dans l'historique Git.
