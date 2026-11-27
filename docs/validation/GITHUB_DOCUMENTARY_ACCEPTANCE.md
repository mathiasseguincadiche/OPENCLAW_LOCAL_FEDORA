# Recette synthétique GitHub documentaire — C02

La campagne Atlas enchaîne les sept lots de C02 sur trois vrais commits
Git locaux. Un service GitHub simulé restitue les arbres, les blobs et
les métadonnées Actions de ces commits. Il reçoit aussi les appels du
publieur de brouillon sous contrôle du test.

| Lot | Preuve contrôlée |
| --- | --- |
| 1. Inventaire | Correspondance entre l'arbre local et l'inventaire GitHub simulé, exclusion des chemins privés et aucun blob lu pendant l'inventaire. |
| 2. Liens | Ancre interne manquante détectée sur le SHA de base, puis corrigée. |
| 3. Cohérence | Version déclarée divergente, puis mise en conformité avec le même contrat. |
| 4. CI | Run réussi sur la révision auditée et référence documentaire à une autre révision détectée. |
| 5. Frontières | Doublon, passage répété et marqueur de diffusion détectés, sans lecture du blob privé. |
| 6. Revue | Six constats rattachés à deux documents. Refus d'une empreinte incorrecte, puis création simulée d'une PR brouillon sur l'empreinte approuvée. |
| 7. Vérification | Les deux blobs approuvés et les six constats sont confirmés sur le commit cible. Un contrôle incomplet laisse la preuve CI à vérifier. |

## Reproduire

Depuis la racine du dépôt, avec Git et les dépendances de test installés :

```bash
export GITHUB_DOCUMENTARY_ACCEPTANCE_EVIDENCE="$(mktemp -d)/github-documentary-c02.json"
GITHUB_SHA="$(git rev-parse HEAD)" pytest -q tests/test_github_documentary_acceptance.py
```

La CI publie le JSON dans l'artefact `github-documentary-c02-synthetic`.
Le rapport identifie le commit de ClawFedora réellement exécuté par la
CI, les SHAs du dépôt Atlas de test, les empreintes des sept lots et les
verdicts du parcours complet et du contrôle incomplet. L'empreinte
du rapport et le verdict figurent dans les journaux du job `quality`.

La clôture porte sur le périmètre logiciel synthétique. La campagne
ne publie ni ne fusionne de PR sur GitHub. Les droits, l'accès à un
dépôt cible et le poste Fedora demandent leur propre réception.
