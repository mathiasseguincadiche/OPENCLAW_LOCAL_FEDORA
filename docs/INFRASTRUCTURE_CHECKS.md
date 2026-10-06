# Relier le mentor aux vérifications de la CI

Les agents préparent et expliquent les contrôles. L’apprenant les exécute dans son exercice ou sa CI GitHub/GitLab. Les résultats restent attachés au commit et aux fichiers contrôlés. Un pipeline vert pour un lint ne prouve pas un déploiement ni une restauration.

| Besoin | Contrôle utile | Ce qu’il reste à vérifier |
|---|---|---|
| Terraform | fmt, validate après init maîtrisé, revue du plan | identité/providers, changements réels, état et coût avant apply |
| Ansible | ansible-lint, syntax-check, check-mode si adapté | exécution isolée et deuxième passage pour l’idempotence |
| Docker | validation Compose, construction et test du service | ports, volumes, santé réelle et secrets |
| Kubernetes | kubeconform, helm lint/template selon le dépôt | sondes, ressources, réseau, déploiement et rollback |
| Sécurité | Gitleaks, Trivy au périmètre choisi | contexte du risque, faux positifs et correction |
| Exploitation | smoke test et restauration isolée | fonctionnalité, données, temps de récupération et limites |

Choisir uniquement les contrôles utiles à l’étape; figer les outils/images et conserver versions, commit, commande, code retour et périmètre. Les rapports peuvent contenir des informations sensibles: importer une version expurgée.

Le plugin local fournit désormais `clawfedora_ci_report`. Avec `format=terraform-validate`, il interprète le JSON issu de `terraform validate -json`. Avec `format=ci-checks`, il accepte un résumé explicitement préparé :

```json
{
  "checks": [
    {"tool": "terraform", "exit_code": 0},
    {"tool": "ansible-lint", "exit_code": 0},
    {"tool": "restore", "exit_code": 1}
  ]
}
```

Outils reconnus : terraform, ansible-lint, docker, kubeconform, helm, trivy, smoke, restore. Maximum 20 contrôles et 12000 octets. Ces noms décrivent le rapport; ils n’autorisent aucune exécution. Le résultat retourne un hash, des statuts **déclarés** et `verification=UNVERIFIED`. Les journaux bruts et leurs secrets ne sont pas repris. Le spécialiste doit lire les preuves originales et vérifier leur provenance avant de conclure; ce helper n’authentifie pas un job distant.

Les contrôleurs Terraform/Ansible/Kubernetes ne sont pas ajoutés comme services permanents au PC. Aucun accès automatique au cloud, jeton GitHub/GitLab ou shell général n’est fourni aux agents. L’évolution vers un runner d’exécution isolé reste une décision distincte, à justifier par un usage répétitif.
