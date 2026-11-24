# Ornith — boucle réelle édition → tests → correction

Cette fonction couvre le rôle `ingenieur-devops` et les tâches **déjà approuvées** par le worker. Les six agents Qwen restent inchangés. Elle conserve les recherches Internet, GitHub et Notion, sans laisser les conteneurs de validation contacter le réseau.

## Préparation unique de l'opérateur

La recette requiert Fedora, Podman **rootless** et une image OCI contenant les validateurs autorisés, déjà chargée et identifiée par un digest SHA-256. Le choix/installation de cette image reste une opération humaine.

```bash
python -m clawfedora.devops_sandbox \
  --runtime /chemin/vers/runtime \
  --image registry.example/validators@sha256:<DIGEST_REEL_64_HEX>

python -m clawfedora.devops_sandbox \
  --runtime /chemin/vers/runtime \
  --image registry.example/validators@sha256:<DIGEST_REEL_64_HEX> --apply
```

Les chemins et digest ci-dessus sont des exemples, pas une image publiée.
Pour Terraform, préparer dans l'image approuvée un miroir de providers compatible
avec les versions et l'architecture cible sous `/opt/clawfedora/terraform-providers`.
Inclure le verrou `.terraform.lock.hcl` du module racine dans le snapshot,
avec les sommes de contrôle pertinentes. Aucun téléchargement automatique.
La qualification de cette image sur Fedora reste à réaliser. Après approbation, l'outil peut effectuer plusieurs validations sans demander une nouvelle confirmation par itération.

## Appels de l'agent

Le `scope` doit être exactement un snapshot scellé de la tâche courante, au format `projects/<projet>/<tâche>/<session>` relativement au workspace de l'agent.

1. `clawfedora_sandbox_iterate(scope=..., operation="inspect", expected_revision="initial")`
2. `clawfedora_sandbox_iterate(scope=..., operation="edit_test", expected_revision="initial", validator="shellcheck", files={"script.sh":"...contenu intégral..."})`
3. En cas d'échec, analyser `log`, puis appeler le même outil avec le dernier `revision` comme `expected_revision` et les fichiers corrigés. Les modifications précédentes sont conservées dans un worktree privé du runtime.
4. Pour une même révision, utiliser `validators=["terraform-validate", "shellcheck"]` à la place de `validator` si ces deux types de fichiers existent. Deux à trois validateurs distincts, chacun dans son propre conteneur (40 s par contrôle), mêmes contrôles à chaque correction. Le reçu conserve le résultat individuel de chaque outil ; aucune référence n'est émise si l'un échoue. Le contrôle unitaire reste disponible (180 s).
5. En cas de PASS, intégrer les références `@tool-sandbox:<id>:<sha256>` retournées dans le JSON `files` de la réponse de tâche. Les noms des fichiers doivent correspondre aux noms des livrables attendus.

Le worker vérifie le reçu PASS émis pendant **cette session et pour ce snapshot exact**, la correspondance du nom et l'empreinte du fichier avant de collecter les octets inclus dans le snapshot validé. Un PASS concerne uniquement le ou les validateurs choisis, pas tous les tests possibles. Le validateur
`terraform-validate` enchaîne formatage, initialisation hors réseau sans backend
et validation de la même copie ; une racine absente ou ambiguë est refusée.
Si l'initialisation échoue, contrôler d'abord le miroir, le verrou et les modules,
plutôt que modifier un code valide. Les dossiers exclus et chemins non canoniques sont refusés. Les outils d'exécution exigent la tâche DevOps active ; une discussion ordinaire ne peut pas relancer un ancien snapshot. Les livrables demeurent soumis aux contrôles, à l'audit et à la validation humaine. Le snapshot initial, le dépôt GitHub et la machine hôte ne sont pas modifiés par l'agent.

## Limites et sécurité

Les validateurs disponibles sont `terraform-fmt`, `terraform-validate`, `ansible-lint`, `actionlint`, `shellcheck`, `hadolint`, `kubeconform` et `pytest` (tests Python du répertoire `tests/`). Ce sont des commandes prédéfinies : aucune commande shell arbitraire fournie par l'agent, `terraform apply`, déploiement ou accès direct aux secrets. Les conteneurs sont éphémères, sans réseau, avec limites CPU/RAM/PID/temps. Trois tentatives maximum par snapshot, chacune comprenant un à trois contrôles. Les tests de référence existants et les
fichiers de configuration de tests sont protégés contre les corrections du producteur ;
les nouveaux tests restent possibles. Ce garde-fou ne remplace pas une recette
indépendante. Pytest exécute le code des tests dans le conteneur isolé.

**Statut de recette :** la CI couvre les contrats et la mécanique de la boucle avec Podman simulé. La qualification réelle sur Fedora, l'image de validateurs et le GPU Intel Arc B580 reste à mener sur la machine cible. Ne pas confondre « PR fusionnée », « tests unitaires verts » et « validation matérielle réelle ».
