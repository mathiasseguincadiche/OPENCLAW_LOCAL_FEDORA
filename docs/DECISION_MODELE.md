# Quel modèle pour expliquer : GLM (cloud) ou Qwen (local) ?

Décision du 9 octobre 2026, prise sur des sources publiques lues ce jour-là. Elle se révise après le premier essai sur le PC (voir « Comment la réviser »).

## La question

Pour **apprendre le métier** (explications justes, vulgarisées, accessibles à un débutant), faut-il le modèle local **Qwen 3.5 9B** ou le modèle cloud **GLM-5.3 Flash** ?

## Ce que disent les sources

| Critère | Qwen 3.5 9B (local) | GLM-5.3 Flash (cloud) | Source |
|---|---|---|---|
| **Fiabilité des faits sans recherche** (AA-Omniscience : part de réponses fausses quand il ne sait pas) | **82 %** de réponses fausses, 14,7 % de réponses justes | **28 %** de réponses fausses | [Artificial Analysis, petits Qwen3.5](https://artificialanalysis.ai/articles/qwen3-5-small-models) ; [Artificial Analysis sur GLM-5.3 Flash](https://x.com/ArtificialAnlys/status/2092663573021606119?lang=en) et [fiche OpenRouter](https://openrouter.ai/z-ai/glm-5.3-flash) |
| Intelligence globale (Artificial Analysis) | 32 sur l'article des petits Qwen3.5 (une autre page du même site donne 11 : versions d'indice différentes) | 57 | mêmes sources |
| Score agrégé (llm-stats) | 24,7 | 49,4 (les deux modèles n'ont aucun test en commun : indice composite) | [llm-stats](https://llm-stats.com/models/compare/glm-5.3-flash-vs-qwen3.5-9b) |
| Taille | 9 milliards de paramètres | 320 milliards, dont 18 actifs par jeton | [llm-stats](https://llm-stats.com/models/compare/glm-5.3-flash-vs-qwen3.5-9b) |
| Tests académiques (MMLU-Pro, GPQA) | 82,5 et 81,7, chiffres du fabricant | non comparés ici | [fiche Hugging Face](https://huggingface.co/Qwen/Qwen3.5-9B) ; [XDA](https://www.xda-developers.com/qwen-3-5-9b-tops-ai-benchmarks-not-how-pick-model/) rappelle que ces tests disent peu de l'usage réel |
| Prix | gratuit (ton PC) | environ 0,15 $ / 0,50 $ par million de jetons (varie selon les pages et les hébergeurs) | [DeepInfra](https://deepinfra.com/blog/glm-5-3-flash-pricing-providers-cost) |

**Lecture.** Le chiffre le plus important pour « des explications correctes » est le taux d'hallucination : face à une question dont il ignore la réponse, Qwen 9B invente dans 82 % des cas, GLM dans 28 %. Ce test mesure la mémoire du modèle, **sans recherche Web**.

## Ce que les sources ne disent pas

- **Aucune comparaison directe GLM-5.3 Flash contre Qwen 3.5 9B sur la pédagogie.** Les comparaisons trouvées opposent GLM à un autre Qwen, plus gros.
- **La pédagogie ne se déduit pas du niveau général.** [MathTutorBench](https://arxiv.org/abs/2502.18940) note que savoir résoudre n'implique pas savoir enseigner ; [TutorBench](https://arxiv.org/pdf/2510.02663) trouve qu'aucun modèle de pointe ne dépasse 56 %, et 47 % pour l'explication adaptée ; [CSTutorBench](https://arxiv.org/pdf/2607.05571) suggère que la famille du modèle et son réglage pèsent plus que la taille. La qualité d'une explication dépend aussi des consignes du mentor ([EduClaw-Bench](https://arxiv.org/html/2608.03206) : le modèle **et** son cadre comptent).
- **L'effet de la recherche Web.** Elle aide beaucoup les petits modèles ([Chinese SimpleQA](https://arxiv.org/pdf/2411.07140) : un modèle de 3 milliards est plus que triplé), mais de mauvais passages dégradent les réponses ([étude sur la récupération](https://arxiv.org/pdf/2402.13492)). Ici la recherche est gratuite, limitée à 4 résultats et à 4 000 caractères par page, et **jamais essayée sur ta machine**.
- **Les données chez le fournisseur.** Je n'ai trouvé aucune source sur la conservation des données de Z.ai pour ce modèle. Voir la vérification à faire plus bas.
- Beaucoup de chiffres sont ceux des fabricants ou de sites de comparaison ; l'indépendant le plus utile ici est Artificial Analysis.

## La décision

| Usage | Modèle | Pourquoi |
|---|---|---|
| **Apprendre** : questions publiques, notions, « comment ça marche » | **GLM-5.3 Flash (cloud)** | Le seul écart mesuré va dans ce sens, et il est grand : 28 % contre 82 % d'invention. Pour un débutant, une explication fausse énoncée avec assurance coûte plus cher qu'un euro de jetons. |
| **Travail** : tout ce qui touche ton employeur, ton réseau, tes documents, ou dont tu n'es pas sûr | **Qwen 3.5 9B (local)** | Rien ne part ; c'est le seul choix sûr pour le confidentiel. |
| **Projets de l'atelier** | Local par défaut ; cloud projet par projet avec accord | Inchangé. |

La recherche Web reste active pour les deux : elle réduit l'écart sans le supprimer, et elle est ce qui apporte des sources datées.

## Mise en œuvre

Le mentor cloud devient le choix à prendre pour apprendre. Le **rendre le choix par défaut** dans Open WebUI n'a de sens qu'une fois le cloud activé et le test de fumée réussi ([fiche 12](fiches/12-cloud.md)) : tant qu'il n'est pas activé, le modèle cloud n'existe pas. Ce réglage reste donc à faire après ce test.

## Vérifications à faire pendant le test de fumée

1. **Le routage vers un hébergeur qui n'enregistre pas les données.** La passerelle demande à OpenRouter `data_collection: deny`. Si aucun hébergeur de GLM-5.3 Flash ne remplit cette condition, OpenRouter répondra qu'aucun point d'accès ne convient (erreur 404 « no endpoints »). Dans ce cas, le cloud ne marche pas tel quel et il faut **décider en connaissance de cause** : changer de modèle cloud, ou relâcher ce réglage. Ne relâche rien sans avoir lu la politique de données de l'hébergeur retenu.
2. **La qualité réelle.** Pose la même dizaine de vraies questions aux deux modèles et compare, avec un œil de débutant : l'explication est-elle juste, claire, vulgarisée ? Les sources citées existent-elles ?

## Comment la réviser

Revois cette décision si l'un de ces points change : un test montre que Qwen explique aussi bien sur tes questions ; GLM coûte nettement plus que prévu ; la recherche Web locale s'avère très fiable ; ou un hébergeur de GLM est jugé inacceptable pour les données.
