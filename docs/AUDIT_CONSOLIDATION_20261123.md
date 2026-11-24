# Audit de consolidation avant réception — 23 novembre 2026

## Périmètre et référence

Revue ciblée du code après fusion de #260 : `da030c8f8c0375099c74a71f95957e103fba4523`.
La CI du commit testé `4424d3099a7257b209aceb918cfa54254bc1caf7` a
réussi 15 contrôles, 1 426 tests, un ignoré, couverture 81 %.
Il ne s'agit pas d'une nouvelle exécution sur le poste.

| Constat | Impact | Correctif dans ce lot |
| --- | --- | --- |
| Benchmark non enregistré sans verrou partagé | Concurrence avec un agent et mesure biaisée | Verrou pour toute mesure, stockage contrôlé et runtime géré |
| Contrôles courts avec inférence hors verrou | Concurrence GPU, notamment en maintenance | Verrou commun, réutilisation contrôlée du FD de maintenance |
| Client Ollama commun via urlopen | Redirection et proxy d'environnement possibles | HTTP direct loopback, chemins et méthodes fixes, réponse bornée |
| Sonde GPU accepte une réponse incomplète dans certains modes | Recommandation matérielle insuffisamment fondée | Fin de génération exigée, réponse non vide et VRAM cohérente |
| Fichier spécial à l'emplacement d'un rapport ou de la config SSE | Lecture bloquante | Ouverture non bloquante, contrôle du type et taille |
| Statut et parcours partiellement historiques | Confusion sur la migration locale | Référence #260 et recette native mises à jour |

Les corrections ne bloquent pas les intégrations Web, GitHub ou Notion :
la restriction HTTP porte uniquement sur le client interne Ollama.
Les tests utilisent des données synthétiques. Aucun benchmark réel,
changement de modèle, déploiement, action distante ou essai B580 n'est
effectué par cette revue. Une validation de CI du nouveau lot est requise.

## Limites et suite

Les versions et politiques ont été relues sur la référence indiquée :
les sept rôles, deux alias locaux, absence de route cloud active,
concurrence 1 et contexte nominal 32768 restent inchangés.
Cet audit ciblé ne remplace pas une revue exhaustive de l'ensemble du
dépôt, de toutes les dépendances ou de tous les parcours navigateur.
L'efficacité de l'annulation SSE, l'autonomie réelle d'Ornith, la
qualité documentaire, les intégrations distantes et les performances
restent à réceptionner selon [la recette globale](RECETTE_GLOBALE.md).
Les rapports GPU ne sont pas des attestations cryptographiques.
