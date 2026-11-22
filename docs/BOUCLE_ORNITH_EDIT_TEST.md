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

Les chemins et digest ci-dessus sont des exemples, pas une image publiée. Après approbation, l'outil peut effectuer plusieurs validations sans demander une nouvelle confirmation par itération.

## Appels de l'agent

Le `scope` doit être exactement un snapshot scellé de la tâche courante, au format `projects/<projet>/<tâche>/<session>` relativement au workspace de l'agent.

1. `clawfedora_sandbox_iterate(scope=..., operation="inspect", expected_revision="initial")`
2. `clawfedora_sandbox_iterate(scope=..., operation="edit_test", expected_revision="initial", validator="shellcheck", files={"script.sh":"...contenu intégral..."})`
3. En cas d'échec, analyser `log`, puis appeler le même outil avec le dernier `revision` comme `expected_revision` et les fichiers corrigés. Les modifications précédentes sont conservées dans un worktree privé du runtime.
4. En cas de PASS, intégrer les références `@tool-sandbox:<id>:<sha256>` retournées dans le JSON `files` de la réponse de tâche. Les noms des fichiers doivent correspondre aux noms des livrables attendus.

Le worker vérifie le reçu PASS émis pendant **cette session**, la correspondance du nom et l'empreinte du fichier avant de collecter les octets **réellement testés**. Les livrables demeurent soumis aux contrôles, à l'audit et à la validation humaine. Le snapshot initial, le dépôt GitHub et la machine hôte ne sont pas modifiés par l'agent.

## Limites et sécurité

Les validateurs disponibles sont `terraform-fmt`, `terraform-validate`, `ansible-lint`, `actionlint`, `shellcheck`, `hadolint`, `kubeconform` et `pytest` (tests Python du répertoire `tests/`). Ce sont des commandes prédéfinies : aucun shell arbitraire, code applicatif arbitraire, `terraform apply`, déploiement ou accès direct aux secrets. Les conteneurs sont éphémères, sans réseau, avec limites CPU/RAM/PID/temps. Trois validations maximum par snapshot.

**Statut de recette :** la CI couvre les contrats et la mécanique de la boucle avec Podman simulé. La qualification réelle sur Fedora, l'image de validateurs et le GPU Intel Arc B580 reste à mener sur la machine cible. Ne pas confondre « PR fusionnée », « tests unitaires verts » et « validation matérielle réelle ».
