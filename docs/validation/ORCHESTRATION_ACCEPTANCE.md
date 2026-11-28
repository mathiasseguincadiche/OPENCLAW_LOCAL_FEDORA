# Recette synthétique de l'orchestration — C03

La campagne Atlas exécute une mission de sauvegarde dans un projet
local temporaire. Le chef des opérations, les producteurs et
l'auditeur retournent des réponses de test. Le plan, les bundles, les
preuves, les révisions et les transitions passent par le code de
ClawFedora.

| Étape | Contrôle |
| --- | --- |
| Choix des rôles | Le chef justifie les rôles proposés. L'opérateur retire une tâche et approuve les trois contributions utiles. |
| Reprise | Le worker s'arrête après avoir écrit l'historique. La reprise conserve le bundle et le numéro de tentative sans rappeler le premier producteur. |
| Transmission | Le destinataire reçoit le manifeste vérifié et la version attendue avant et après la correction. |
| Preuve obligatoire | L'auditeur reste bloqué tant que le projet n'a pas le reçu de l'observation synthétique. |
| Correction | Seul le producteur ciblé reçoit le constat en échec et sa version précédente. Une correction inchangée s'arrête. Une nouvelle décision humaine permet la reprise. |
| Nouvel audit | Les sessions de validation et de relecture voient les fichiers corrigés. Le dossier atteint `COMPLETE` après l'approbation finale. |

## Reproduire

Exécuter ces commandes depuis la racine du dépôt, avec les dépendances
de test installées.

```bash
export CLAWFEDORA_ORCHESTRATION_ACCEPTANCE_EVIDENCE="$(mktemp -d)/orchestration-c03.json"
GITHUB_SHA="$(git rev-parse HEAD)" pytest -q tests/test_orchestration_acceptance.py
```

La CI publie le JSON dans l'artefact `orchestration-c03-synthetic`.
Le rapport identifie le commit exécuté, le verdict des six étapes et
les empreintes des pièces de preuve. Le job `quality` vérifie également
l'empreinte de ce rapport.

La campagne couvre l'orchestration logicielle avec des agents simulés.
La réception sur Fedora et l'évaluation des modèles locaux suivent
leurs propres campagnes.
