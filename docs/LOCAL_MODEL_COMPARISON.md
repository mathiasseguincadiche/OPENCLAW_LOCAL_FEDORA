# Comparaison réelle des deux modèles locaux sur CPU distant

Le workflow manuel `Local model comparison (CPU)` utilise deux runners Linux standards
indépendants, chacun chargeant un seul des modèles déclarés : Qwen 3.5 9B Q4_K_M ou
Ornith 1.5 9B Q4_K_M. Le dépôt public utilise des runners standards gratuits selon
[la documentation GitHub](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
Aucun GPU payant, compte IA, clé API, service d'inférence cloud ni donnée personnelle.

Le mode ciblé est déclenché par un push sur la branche interne feat/local-model-targeted.
Le mode smoke reste accessible manuellement. Après fusion, lancer manuellement depuis Actions → Local model comparison
(CPU) → Run workflow. Ne pas utiliser le workflow sur des dépôts privés ou des runners payants.

| Mode | Cas métier par modèle | Total des deux modèles |
| --- | ---: | ---: |
| smoke | 2 (DevOps et audit) | 4 |
| pilot | 7 (tous les rôles) | 14 |
| extended | 14 (deux suites existantes) | 28 |

Chaque modèle dispose en plus d'une sonde d'appel d'outil synthétique (au plus deux
inférences) et d'une sonde JSON/Bash contrôlée par ShellCheck (aucune exécution du script).
La suite de 35 cas par modèle envisagée initialement sera étendue seulement après
mesure de faisabilité. Limite 90 minutes par runner ; un timeout peut laisser une campagne
incomplète. Les résultats intermédiaires sont enregistrés à chaque réponse.

Les prompts reprennent les fichiers SOUL/AGENTS et les contrats partagés du dépôt,
avec une restriction explicite des outils. Même contexte 8192, budget 1200 tokens en smoke, 1800 en pilot/extended (sondes : 1200),
température 0, seed 42, CPU 4 threads, thinking désactivé pour ce premier profil.
Il ne s'agit pas d'une session OpenClaw complète ; aucun outil réel GitHub/Notion
n'est appelé et le résultat de l'outil de test est une fixture connue, pas un scan.
La sonde Bash vérifie la forme JSON et le lint, pas le comportement du script.

L'archive Ollama est contrôlée avec le manifeste d'intégrité du dépôt, sa version est
vérifiée via API et les modèles sont téléchargés par Ollama sur leur tag exact ;
le digest et la quantification observés sont enregistrés. Ces tags ne sont pas
immuables : comparer les empreintes entre campagnes. Refus si modèle différent.

Les rapports contiennent les réponses synthétiques, les identifiants, SHA de suite,
SHA Git, métriques de génération, état des sondes et limites. Les artefacts publics
ne contiennent que des données synthétiques ; rétention trois jours. Aucun score
sémantique automatique, aucun changement de routage. Examiner les attendus dans
`config/evals/infraops_reference.yaml` et `devops_synthetic.yaml`, noter exactitude,
clarté, preuves et sécurité séparément. Une réponse tronquée ou un échec est conservé.
Les temps CPU ne sont pas des mesures de la B580, et les scores sur ces cas ne certifient
ni l'orchestration native ni l'usage de vrais outils. Qualifier ensuite localement sur Fedora.

## Retour du premier smoke réel

[Run 45753983855](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45753983855).
Les deux modèles ont répondu, passé la sonde d'outil et le contrôle statique Bash.
Trois réponses métier sur quatre se sont arrêtées sur la limite de 1200 tokens.
Le pilote exige des réponses concises et relève séparément les troncatures ;
les résultats d'un profil différent ne sont pas comparables en vitesse brute.
Ne pas confondre arrêt normal, qualité du contenu et validation technique.
Le contrôle statique Bash ne démontre pas le comportement du script.
Le pilote conserve le plafond de 90 minutes par runner et peut être incomplet.

## Campagne ciblée sur les erreurs du pilote

Le [pilote 45756209993](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45756209993)
a collecté 14 réponses : Qwen 5/7 arrêts normaux, Ornith 7/7. Les deux
modèles ont passé la sonde d'outil synthétique et ShellCheck, mais les
réponses présentent des erreurs de fond sur libvirt, Docker, Borg et PostgreSQL.

Le mode `targeted` utilise les notes documentaires synthétisées et datées
dans `config/evals/targeted_sources.json`. Les références libvirt 0.9.0,
Borg 1.4.5 et PostgreSQL 17 sont des versions de test, pas des changements de
versions du projet. Les pages Docker/HashiCorp non versionnées sont
référencées à la date de consultation, et les notes sont figées par Git.

Chaque cas comporte quatre faits à contrôler et trois étapes :
sans sources, avec sources (nouvelle conversation), puis correction de
cette réponse avec la liste réelle des champs en échec. La troisième
étape ne révèle pas les réponses attendues dans le retour du validateur.
Elle conserve les notes fournies à la deuxième étape. Les deux modèles
utilisent les mêmes paramètres, 600 tokens de sortie et thinking désactivé.
Le digest doit rester identique à celui du pilote.

La grille vérifie des champs JSON et la forme exacte des commandes
minimales demandées, pas leur exécution. Elle exclut une déclaration
d'exécution et un arrêt tronqué du PASS de contrat. Les justifications
restent à relire : une contradiction en texte libre n'est pas détectée
automatiquement. Ce test mesure une capacité étroite de restitution et
de correction, pas la maîtrise d'un déploiement. Aucune action Terraform,
Docker, Borg ou PostgreSQL n'est exécutée. Aucun changement de routage.
Quatre cas × trois étapes × deux modèles = 24 appels bornés. Le rapport
partiel est conservé si une inférence échoue.

## Résultats réels et réévaluation du contrat

[Run 45763150523](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/45763150523),
24 réponses terminées, mêmes digests que le pilote, aucune déclaration
d'exécution positive. Les réponses JSON et les verdicts originaux sont
conservés dans le fixture `tests/fixtures/targeted_comparison_45763150523.json`
à partir des logs publics (jobs 139717647773 et 139717648392).

Le validateur initial a rejeté DNAT, alors que la traduction de destination
est correcte pour la publication de ports Docker en mode bridge NAT.
Référence : [Docker avec iptables](https://docs.docker.com/engine/network/firewall-iptables/).
La révision 2 accepte NAT et DNAT, mais pas SNAT ni iptables seul.
La suite et les réponses d'origine ne changent pas ; un test rejoue
les 24 observations sans inférence. Les scores bruts restent conservés.

| Modèle | Sans sources (brut → révisé) | Sources | Correction |
| --- | ---: | ---: | ---: |
| Qwen | 7 → 7/16 | 15 → 16/16 | 15 → 15/16 |
| Ornith | 9 → 10/16 | 13 → 14/16 | 14 → 15/16 |

Qwen a ajouté `--stats` à `borg check` lors de la correction alors que
la réponse précédente était correcte. Ornith n'a pas trouvé la syntaxe
de création Borg 1.4.5, même après retour du validateur.
Voir [borg check](https://borgbackup.readthedocs.io/en/1.4.5/usage/check.html).
Une révision peut donc dégrader un résultat déjà correct ; ne pas lancer
une correction inutile en production, et ne promouvoir une version
révisée qu'après contrôle des exigences et absence de régression.

Conclusion provisoire : conserver les deux modèles et le routage actuel.
Les notes fournissent directement les faits demandés ; cette campagne
mesure leur exploitation, pas une recherche autonome ni une expertise
opérationnelle. Les quatre cas ne permettent pas une sélection définitive.
La qualification sur Fedora/B580, les outils réels et les tests
d'intégration restent nécessaires.
