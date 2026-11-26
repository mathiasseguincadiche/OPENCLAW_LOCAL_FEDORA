# Qualification approfondie des finalistes — Boréal

Suite de [la présélection Atlas](EXCELLENCE_SCREENING_RESULTS_45769070175.md).
Trois candidats, sept nouveaux cas métier fictifs, deux répétitions indépendantes
(seed 42 et 73). Même dossier par rôle pour chaque modèle ; aucun transfert de
conversation entre répétitions. Les notes documentaires fournies sont des
fixtures explicites et non une recherche web autonome. La convention Terraform
est vérifiable dans la [documentation du plan](https://developer.hashicorp.com/terraform/cli/commands/plan).
Aucune donnée personnelle ni source privée.

| Paramètre | Valeur |
| --- | --- |
| Modèles | Qwen 3.5 9B, Ornith 1.5 9B, Gemma 4 12B, mêmes digests observés |
| Runtime | Ollama verrouillé, CPU 4 threads, contexte 8192, Q4_K_M |
| Raisonnement | demandé si capacité thinking déclarée par /api/show ; présence de sortie thinking enregistrée, pas son texte |
| Budget | 1800 tokens par appel ; livrable reason limité à 1200 caractères |
| Répétitions | 2 par cas, seeds 42 et 73, température 0 (des résultats identiques sont possibles) |
| Runners | 12 jobs : 3 modèles × 2 seeds × 2 lots (4 et 3 rôles) |
| Appels | 42 initiaux, au plus 42 corrections ciblées ; 150 min max par job |

La campagne démarre sur la branche interne feat/excellence-finalists, puis
reste lançable manuellement. Les rapports intermédiaires sont enregistrés et
imprimés dans les logs à chaque étape. Un timeout ou refus de capacité reste
un échec expérimental ; aucune bascule silencieuse vers un autre profil.
La présence de thinking ne prouve pas sa qualité, et les profils peuvent différer
selon les capacités natives du modèle. Le temps CPU inter-machines n'est pas
un classement GPU.

Le validateur sépare JSON invalide, clés manquantes/supplémentaires, types,
longueur, faits faux, exécution déclarée et complétude. La correction reçoit
les écarts, pas les valeurs attendues. Aucun passage correct n'est réécrit.
Les contrats réussis restent soumis à la lecture du livrable, de ses contradictions,
de ses preuves et de ses limites, avec la grille pondérée existante. Pas de score
automatique, aucun statut excellence. Les scénarios ne démontrent pas les
appels d'outils OpenClaw, la recherche réelle, les commandes ou la B580.

Après collecte : archiver les 12 rapports, comparer la stabilité par rôle,
examiner manuellement le texte et les contradictions, puis choisir les profils
à qualifier sur des cas supplémentaires et sur les outils natifs. Le minimum
de trois répétitions de qualification finale n'est pas atteint par cette
campagne seule. Aucun changement du catalogue, des agents ni du routage.
