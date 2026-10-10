# Quel modèle pour expliquer et travailler : DeepSeek (cloud) ou Qwen (local) ?

Décision mise à jour le **10 octobre 2026**. Elle remplace le choix GLM-5.3 Flash fait la veille, sans changer l'architecture de sécurité : le local reste le choix par défaut, le cloud reste facultatif et passe toujours par la passerelle locale.

## La question

Pour apprendre le DevOps, relire un dépôt, raisonner sur une architecture et produire des livrables, quand faut-il utiliser **Qwen 3.5 9B en local** et quand faut-il utiliser **DeepSeek V4.1 Flash dans le cloud** ?

## Ce qui est établi

| Critère | Qwen 3.5 9B (local) | DeepSeek V4.1 Flash (cloud) |
|---|---|---|
| Confidentialité | Les conversations restent sur le PC, hors recherche Web demandée. | Le contenu autorisé passe par OpenRouter après filtrage local. |
| Coût marginal | Pas de coût API. | Facturé à l'usage, avec plafond local de 25 € par mois. |
| Capacité | Modèle compact adapté au quotidien, à la rédaction et aux petites tâches. | Modèle beaucoup plus grand, conçu pour le code, les outils et les tâches agentiques longues. |
| Outils | Pris en charge par OpenClaw. | Pris en charge par le modèle et par OpenRouter. |
| Contexte utilisé par ce projet | 32 768 tokens. | 32 768 tokens, volontairement limité par le projet malgré un contexte fournisseur bien plus grand. |
| Images dans ce projet | Autorisées en local. | **Interdites pour l'instant**, même si le modèle les accepte : le filtre de confidentialité ne sait pas inspecter une image. |

DeepSeek annonce pour V4.1 Flash notamment **90,6 sur Terminal-Bench 2.1**, **74,2 sur DeepSWE v1.1** et **65,4 sur NL2Repo-Bench**. Ce sont des indicateurs intéressants pour un atelier DevOps et des agents de code, mais ils ne prouvent pas qu'il enseigne mieux à un débutant.

Sources :
- DeepSeek, annonce V4.1 Flash : https://deepseek.com/en/news/deepseek-v4-1-flash/
- DeepSeek API, changelog : https://api-docs.deepseek.com/updates/
- OpenRouter, modèle épinglé : https://openrouter.ai/deepseek/deepseek-v4.1-flash

## Ce qui n'est pas établi

- Il n'existe pas ici de benchmark direct et fiable **Qwen 3.5 9B vs DeepSeek V4.1 Flash sur la pédagogie DevOps**.
- Les scores publics ne remplacent pas un essai sur les vraies questions de l'utilisateur.
- Le projet n'a pas encore effectué d'appel réel à OpenRouter sur le PC cible.
- La qualité du routage avec `data_collection: deny`, les coûts réels et le comportement de l'hébergeur doivent encore être vérifiés par le test de fumée.
- Les benchmarks du fabricant et les agrégateurs sont utiles pour orienter un choix, pas pour promettre un résultat.

## La décision

| Usage | Modèle | Raison |
|---|---|---|
| Questions courantes, rédaction simple, travail confidentiel | **Qwen 3.5 9B local** | Gratuit, immédiat et aucune donnée métier n'est envoyée à un modèle distant. |
| Explication publique complexe, longue analyse, revue de dépôt, architecture, code ou tâche agentique difficile | **DeepSeek V4.1 Flash cloud** | Plus de capacité et de meilleurs signaux publics sur le code, les outils et les tâches longues. |
| Projet contenant des données internes, un réseau réel, des identifiants ou un doute sur la confidentialité | **Qwen local** | Le filtre arrête les secrets évidents, pas toute information confidentielle. |
| Atelier Projets | Local par défaut ; cloud uniquement après accord du projet | Le consentement et le digest des sources restent obligatoires. |

Le cloud n'est donc **pas** un repli automatique de Qwen. C'est un choix explicite pour une tâche où sa valeur justifie l'envoi et le coût.

## Pourquoi garder OpenRouter

La migration change le modèle, pas la passerelle. OpenClaw continue à parler à `cloudgw`, la passerelle locale continue à :

1. vérifier l'activation du cloud ;
2. filtrer l'intégralité de la requête et les résultats d'outils ;
3. réserver le budget avant l'appel ;
4. imposer les paramètres fournisseur ;
5. envoyer vers OpenRouter ;
6. compter le coût réel renvoyé par le fournisseur ;
7. refuser en mode fail-closed si un garde-fou manque.

Le modèle est épinglé à **`deepseek/deepseek-v4.1-flash`**. On n'utilise pas un alias « latest » afin qu'une nouvelle version ne remplace pas silencieusement le modèle validé.

## Pourquoi les images restent locales

DeepSeek V4.1 Flash accepte les images, contrairement à l'ancien modèle cloud utilisé dans le projet. Cela ne suffit pas pour les activer.

Le filtre actuel travaille sur le contenu textuel de la requête. Une capture d'écran peut contenir un mot de passe, une adresse interne, un nom d'employeur ou un identifiant que le filtre ne verrait pas. Tant qu'une chaîne locale d'inspection/redaction d'image n'existe pas, **une image ne part pas au cloud**.

## Passage futur à DeepSeek V4.1 Pro

Le projet est volontairement préparé pour que ce passage reste petit :

- les sept rôles utilisent l'alias logique `cloud-main`, pas un nom de modèle codé dans leurs prompts ;
- l'interface affiche « cloud (DeepSeek) », pas « Flash » ;
- le consentement utilise un scope générique `cloud-deepseek` ;
- le modèle réel reste épinglé dans la politique centrale ;
- le texte de consentement est haché : changer de modèle force naturellement à renouveler l'accord d'un projet.

On passera à V4.1 Pro seulement si les cinq points suivants sont vrais :

1. sortie officielle et stable ;
2. disponibilité sur le fournisseur retenu ;
3. support fiable des outils utilisés par OpenClaw ;
4. politique de données compatible avec les garde-fous du projet ;
5. coût compatible avec le plafond mensuel et gain mesuré sur les tâches réelles.

Le changement devra alors être explicite, testé dans une pull request, puis validé par le même test de fumée que Flash.

## Vérifications à faire au premier essai

1. Activer le cloud avec les deux garde-fous validés.
2. Vérifier qu'OpenRouter accepte `data_collection: deny` pour DeepSeek V4.1 Flash.
3. Poser les mêmes dix questions DevOps à Qwen local et DeepSeek cloud.
4. Comparer : exactitude, clarté, niveau pédagogique, citations, qualité du code et temps de réponse.
5. Lancer une tâche avec outil et vérifier que chaque appel est compté.
6. Vérifier le coût réel dans OpenRouter puis exécuter le rapprochement local.
7. Vérifier qu'un secret dans un message ou un résultat d'outil bloque bien le second envoi.

## Règle pratique

**Local par défaut. DeepSeek quand la tâche est publique et réellement difficile. Aucune donnée sensible au cloud par confort.**

Cette règle pourra être revue après les premières mesures réelles sur le PC Fedora.
