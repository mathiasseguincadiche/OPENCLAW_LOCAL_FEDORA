# Choisir le modèle du mentor OPS — 6 octobre 2026

**Décision : conserver Qwen 3.5 9B Q4_K_M comme modèle quotidien unique.** C’est le compromis recommandé pour Ryzen 7 7700, 48 Gio de RAM et Arc B580 12 Gio, au vu des sources disponibles. Ce choix n’est pas une qualification de la machine : aucune inférence Fedora/B580 n’a été exécutée dans cette intervention, réalisée depuis WSL.

## Trois candidats pertinents

| Modèle exact Ollama | Paquet annoncé | Intérêt | Décision |
|---|---:|---|---|
| `qwen3.5:9b-q4_K_M` | 6,6 GB ≈ 6,15 Gio | polyvalence, appels d’outils et marge mémoire | quotidien |
| `gemma4:12b-it-q4_K_M` | 8,0 GB ≈ 7,45 Gio | challenger code et explications à évaluer | expérimental |
| `granite4.2:8b-q4_K_M` | 5,3 GB ≈ 4,94 Gio | poids plus petits, orientation code/agents | expérimental |

Sources : tags exacts [Qwen](https://ollama.com/library/qwen3.5:9b-q4_K_M), [Gemma](https://ollama.com/library/gemma4:12b-it-q4_K_M), [Granite](https://ollama.com/library/granite4.2:8b-q4_K_M), consultés le 6 octobre 2026. Les tags peuvent changer : le digest observé doit rester tracé. Le téléchargement inclut selon le modèle des composants annexes; **taille du paquet et VRAM occupée ne sont pas équivalentes**.

La mémoire réelle comprend poids, cache de contexte, buffers et bureau graphique. Qwen 9B alterne attention linéaire et attention complète; Granite 4.2 8B utilise une architecture dense à attention complète. Un paquet plus petit ne garantit donc pas une empreinte plus petite à tout contexte. Cette différence motive une mesure, pas une estimation de performances. Les détails viennent des fiches [Qwen 9B](https://huggingface.co/Qwen/Qwen3.5-9B) et [Granite 8B](https://huggingface.co/ibm-granite/granite-4.2-8b).

Des modèles de 27B et davantage dépassant les 12 Gio en Q4 demandent un partage CPU/GPU. Les 48 Gio de RAM rendent certains chargements possibles, sans préserver forcément la réactivité du mentor ni celle des VM DevOps. Ce n’est pas la cible quotidienne. Sept rôles réutilisent le même modèle séquentiellement : sept profils ne multiplient pas ses poids par sept.

## Ce que les tests publiés disent réellement

Scores déclarés par les fabricants dans les **fiches des tailles exactes**, et non dans le README générique d’une famille :

| Évaluation | Qwen 9B | Gemma 12B | Granite 8B |
|---|---:|---:|---:|
| MMLU-Pro, connaissances/raisonnement | 82,5 | 77,2 | 74,04 |
| LiveCodeBench v6, problèmes de programmation | 65,6 | 72,0 | 73,24 |
| BFCL v4, appels de fonctions | 66,1 | non publié dans cette fiche | 52,39 |

Sources : [Qwen](https://huggingface.co/Qwen/Qwen3.5-9B), [Google](https://huggingface.co/google/gemma-4-12B-it), [IBM](https://huggingface.co/ibm-granite/granite-4.2-8b). Les protocoles, budgets de raisonnement et configurations diffèrent. Ce tableau n’est **pas un comparatif contrôlé de ces trois modèles Q4 avec thinking désactivé**. Un score de code algorithmique ne mesure pas directement le diagnostic Terraform/Kubernetes ou la pédagogie française. Il montre néanmoins pourquoi Gemma et Granite méritent une comparaison ciblée; Qwen n’est pas présenté comme vainqueur de tout.

Deux travaux indépendants dont les auteurs publient leurs résultats complètent ces fiches :

| Source primaire | Résultat pertinent | Limites |
|---|---|---|
| [Agent Benchmark Suite](https://github.com/JConradoN/local-llm-benchmark) | Qwen 3.5 9B : 3,60/4 au total, 4/4 dans la sélection d’outils | Xeon, 128 GB, deux RTX 3060; critères en partie fondés sur des mots-clés; les autres modèles sont Granite **4.1** et Gemma **E4B**, pas nos challengers exacts |
| [Small LLM Tool Use Bench](https://huggingface.co/Manojb/small-llm-tool-use-bench) | Qwen 9B Q4/Ollama : BFCL 61,3 %, NexusRaven 75 %, AgentBench adapté 45 % | Mac Mini M4 16 GB; petits sous-ensembles et dix tâches AgentBench; aucun test de mentor OPS français sur B580 |

Ces résultats soutiennent Qwen comme base pratique, mais montrent aussi des erreurs et un succès limité sur des tâches à plusieurs étapes. Ils justifient les tâches courtes, les critères explicites et les retours avant de poursuivre. On ne transpose pas leurs tokens/s à la B580. Les calculateurs de compatibilité fondés sur des estimations ne sont pas des benchmarks mesurés.

**Conclusion d’ingénierie : Qwen est le choix initial le mieux défendable pour l’ensemble du besoin, pas un modèle «parfait» démontré.** Gemma ne devient principal que si sa meilleure aide dans nos exercices compense son coût. Granite ne devient principal que si ses résultats français, ses outils et sa réactivité réelle apportent un avantage. Aucun changement automatique du modèle, du digest, du backend ou du contexte.

## Comparaison réalisable sur le PC

La suite `benchmarks/suites/mentor_ops_fr.yaml` contient huit situations courtes et trois critères humains par réponse. Elle teste le transfert Linux/réseau vers les pratiques OPS, le diagnostic, une action ciblée et la séparation déclaration/preuve.

Depuis le dépôt et sa venv, préparer uniquement le plan :

```bash
.venv/bin/python -m clawfedora.model_compare --root "$PWD" --output /tmp/mentor-plan.json
```

Après installation explicite des trois candidats, précontrôles Fedora/B580 valides et libération des modèles résidents, mesurer :

```bash
.venv/bin/python -m clawfedora.model_compare --root "$PWD" \
  --runtime-root /srv/openclaw-local --output /tmp/mentor-mesures.json --repeats 2 --live
```

Le programme utilise le verrou commun, l’API Ollama loopback et les versions du contrat. Il refuse candidats absents, quantification divergente, absence d’allocation GPU et changement d’identité. Il ne télécharge rien, ne supprime aucun modèle et ne modifie aucun routage. Il décharge chaque candidat après son passage et refuse d’écraser un rapport existant.

Paramètres communs : contexte alloué 8192, thinking demandé désactivé, température 0,2, top_p 0,8, top_k 20, presence_penalty 0, graines enregistrées par répétition, sortie 1024. La résidence 15 minutes est **un paramètre de l’expérience**; le profil quotidien conserve trois minutes. On peut refaire l’expérience avec `--tokens 1536` ou `--tokens 2048` et un autre fichier. Ces options ne changent jamais le plafond quotidien.

Le rapport conserve réponses brutes, identités, temps de chargement, temps total, débit de génération, raison de fin, allocation résidente et échantillons du pic VRAM total des clients xe accessibles. Une télémétrie inaccessible reste `null`, jamais zéro substitué. Le premier cas inclut le chargement; les suivants réutilisent le modèle, ce qui doit être distingué dans l’analyse. `done_reason=length` signale une réponse tronquée. Aucun score pédagogique automatique.

Lire les réponses sans regarder le nom du modèle si possible. Pour chaque critère : correct, incorrect ou preuve insuffisante; noter l’erreur concrète et l’action proposée. Préférer le modèle qui explique juste, demande la bonne observation et laisse réaliser une étape, tout en gardant le poste utilisable. Répéter quelques cas avec les VM/outils de travail ouverts et observer la fluidité du bureau. Les prompts sont courts : allouer 8K ne constitue pas un stress test avec 8K remplis. Cette comparaison de réponses seules ne remplace ni les tests d’outils natifs OpenClaw ni les gates matériels et projets L4–L8.
