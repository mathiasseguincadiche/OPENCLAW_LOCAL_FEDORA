# Présélection de modèles : objectif excellence des sept agents

## Objectif et périmètre

Obtenir des résultats excellents pour chaque rôle, sans confondre résultat
d'un test étroit, qualification native et certification. Ne pas modifier
le catalogue, le routage ou les dépendances de production pendant cette
présélection. La cible reste Fedora et Intel Arc B580 (12 Go de VRAM).

| Modèle candidat | Tag Ollama | Poids approximatif Q4 | Hypothèse |
| --- | --- | ---: | --- |
| Qwen 3.5 9B | qwen3.5:9b-q4_K_M | 6,6 Go | Généraliste |
| Ornith 1.5 9B | ornith-1.5:9b | 6,6 Go | Code et outils |
| Gemma 4 12B | gemma4:12b-it-q4_K_M | 8 Go | Raisonnement et contre-expertise |
| LFM 2.5 8B-A1B | lfm2.5:8b-a1b-q4_K_M | 5,2 Go | Outils et efficacité |

Références : [Gemma 4](https://ollama.com/library/gemma4/tags),
[LFM 2.5](https://ollama.com/library/lfm2.5/tags),
[MiMo V2.6](https://ollama.com/library/mimo-v2.6).
MiMo est un candidat ultérieur : sa prise en charge officielle est annoncée
dans Ollama 0.40.15, alors que le runtime de production est verrouillé
en 0.40.6. Qwen 3.8 27B à environ 18 Go Q4 n'est pas prioritaire pour
une exécution entièrement en VRAM. Les tailles ne prouvent pas la
compatibilité GPU, le contexte maximal ni les performances.

## Étape 1 — présélection distante

Workflow `Excellence model screening (CPU)` : push ciblé sur
`feat/excellence-model-screening`, puis déclenchement manuel.
Quatre runners standards publics indépendants, un modèle par runner.
Archive Ollama vérifiée par le verrou existant. Les digests de Qwen
et Ornith doivent être identiques au pilote. Les nouveaux digests sont
observés, non pré-certifiés ; la compatibilité de leur tag avec le runtime
reste à constater. Échec de chargement = blocage expérimental, pas
preuve de médiocrité du modèle.

Les sept cas sont dans `config/evals/excellence_screening.json`. Chaque
cas comporte quatre faits évalués automatiquement, plus un court livrable
français à relire. Les modèles utilisent les vrais prompts SOUL, AGENTS
et les contrats partagés, dans un contexte synthétique sans accès à des
données privées. Contexte 8192, 600 tokens de sortie, température 0,
seed 42, CPU 4 threads, thinking désactivé pour la présélection.
Une correction au maximum si le contrat factuel est en échec. Une
réponse conforme est conservée, aucune réécriture superflue. Une
révision non conforme reste bloquée. Sondes synthétiques d'appel
d'outil et de génération JSON/Bash contrôlée par ShellCheck, communes
à chaque modèle ; aucun script généré n'est exécuté.

28 réponses initiales, au maximum 28 corrections et 12 inférences
de sondes, soit 68 appels au maximum. Plafond 120 min par runner.
Rapports intermédiaires conservés ; un échec ou timeout peut laisser
un résultat incomplet. Les artefacts ne contiennent que des données
publiques fictives. Le temps CPU entre machines distinctes n'est pas
un classement matériel fiable.

## Étape 2 — revue et sélection de finalistes

Grille humaine, notes entières 0 à 4 :

| Dimension | Poids |
| --- | ---: |
| Exactitude technique | 25 |
| Raisonnement | 20 |
| Instructions | 15 |
| Outils | 15 |
| Livrable | 10 |
| Correction | 10 |
| Performance | 5 |

La fonction `review_score` reçoit une ligne de rapport, et une revue
avec `row_sha256` (empreinte canonique via `mc._digest`), `scores`,
`blockers` et `notes`. Elle ne génère pas les notes. Un score de 90/100
ou plus indique seulement un candidat à approfondir. Un champ factuel
incorrect ou un blocage humain interdit cette désignation. Les blocages
comprennent erreur technique critique, action dangereuse, preuve
inventée, divulgation privée et action distante non approuvée.
Une note ne doit pas être attribuée à une dimension non observée :
différer la revue complète tant que les preuves manquent. Une sonde
globale ne qualifie pas l'utilisation des outils propres à chaque rôle.
Aucune note ni sélection automatique dans le workflow.

Revoir les textes libres, notamment contradictions avec les champs JSON,
qualité des ADR, pédagogie et exactitude des commandes. Comparer les
finalistes sur de nouveaux scénarios, avec sources non triviales,
raisonnement activé et répétitions ; ne pas réutiliser les questions
déjà apprises comme seule preuve d'excellence. Les scores de cette
présélection ne sont pas comparables aux anciennes campagnes.

## Étape 3 — qualification native

Sur Fedora : mesurer temps de réponse, mémoire et contexte, tester les
outils spécifiques à chaque rôle, sécurité et régressions, preuves
réelles et travail collectif Atlas. Tester les quantifications plus
précises uniquement si elles laissent suffisamment de VRAM pour les
contextes et le système. Un modèle à la fois, sans fallback cloud.
Vérifier chaque finaliste avec au moins trois répétitions et plusieurs
scénarios distincts ; maintenir le duo actuel jusqu'à décision
documentée. Niveau excellent visé >=90/100 pour chaque rôle, sans
blocage critique, et avec preuves natives ; aucune promesse de résultat.

## Résultats de la première campagne

[Audit et replay hors ligne du run 45769070175](EXCELLENCE_SCREENING_RESULTS_45769070175.md).
Les verdicts originaux sont conservés ; aucun changement du routage actif.
