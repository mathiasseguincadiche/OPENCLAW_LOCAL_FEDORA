# Comparaison réelle des deux modèles locaux sur CPU distant

Le workflow manuel `Local model comparison (CPU)` utilise deux runners Linux standards
indépendants, chacun chargeant un seul des modèles déclarés : Qwen 3.5 9B Q4_K_M ou
Ornith 1.5 9B Q4_K_M. Le dépôt public utilise des runners standards gratuits selon
[la documentation GitHub](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
Aucun GPU payant, compte IA, clé API, service d'inférence cloud ni donnée personnelle.

Le pilote est déclenché par un push sur la branche interne feat/local-model-pilot.
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
