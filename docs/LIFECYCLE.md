# Cycle de vie du produit

`OPENCLAW_LOCAL_FEDORA` distingue strictement le **code source complet** des **preuves matérielles**. Le cycle de vie peut être implémenté et testé en CI sans revendiquer un PASS B580 réel.

## Installation complète

Dry-run :

```bash
./menu.sh --action install
```

Application :

```bash
./menu.sh --action install --apply
```

Le chemin d'installation exécute, dans cet ordre :

1. bootstrap Fedora 44 ;
2. création du runtime géré sous `/srv/openclaw-local` ;
3. installation explicite d'Ollama si absent ;
4. installation d'OpenClaw `2026.7.1-2` via l'installateur CLI officiel si nécessaire ;
5. provisionnement explicite des trois modèles nominaux ;
6. déploiement des huit workspaces ;
7. rendu, dry-run puis application de la configuration OpenClaw ;
8. installation du Gateway comme service utilisateur systemd ;
9. health-check final.

L'installation complète doit être lancée depuis le compte Fedora de bureau, jamais directement en root.

## Provisionnement des modèles

Le téléchargement implicite reste interdit pendant les benchmarks. Le téléchargement volontaire est séparé :

```bash
./menu.sh --action models
./menu.sh --action models --apply
```

La commande lit exclusivement `config/model_catalog.yaml`.

## Santé

```bash
./menu.sh --action health
```

Le health-check couvre : contrats du dépôt, runtime root, CLI OpenClaw, Gateway, Ollama, inventaire exact des trois modèles et huit workspaces gérés.

## Sauvegarde et restauration

Sauvegarde :

```bash
./menu.sh --action backup
```

Sont sauvegardés : `state/`, `projects/`, `proofs/`, `workspaces/`.

Sont exclus : les poids de modèles et le virtualenv, qui sont reproductibles. Chaque backup contient `BACKUP_MANIFEST.json` avec SHA-256 de chaque fichier.

Restauration vers une destination **vide** :

```bash
./scripts/linux/12_backup_restore.sh restore ARCHIVE DESTINATION
```

Les chemins absolus, traversées `..`, liens et types spéciaux sont refusés.

## Réparation

Dry-run :

```bash
./menu.sh --action repair
```

Application :

```bash
./menu.sh --action repair --apply
```

La réparation crée d'abord un backup, valide les contrats, exécute `openclaw doctor`, redéploie les workspaces, réapplique la configuration nominale, redémarre le Gateway avec `--preserve-definition`, puis lance le health-check.

## Désinstallation

Dry-run :

```bash
./menu.sh --action uninstall
```

Désinstallation conservatrice :

```bash
./menu.sh --action uninstall --apply
```

Par défaut, projets, modèles et preuves sont préservés. Seuls le service Gateway, les workspaces marqués comme gérés et le virtualenv géré sont retirés.

La purge des données exige deux signaux explicites :

```bash
./menu.sh --action uninstall --apply --purge-data
```

Aucune suppression n'est autorisée hors de la racine runtime sélectionnée.

## Télémétrie

La télémétrie est locale et structurée. Elle n'accepte que les champs autorisés dans `config/core/telemetry_policy.yaml` et refuse prompt, réponse, contenu de document ou secret.

```bash
clawfedora-ops --runtime-root /srv/openclaw-local telemetry \
  --event task.completed --project-id p1 --status PASS
```

## FinOps

Le cloud reste désactivé par défaut. FinOps sert uniquement à enregistrer les escalades cloud explicitement approuvées.

```bash
clawfedora-ops --runtime-root /srv/openclaw-local finops \
  --event reservation --amount-eur 0.25 --reason "approved escalation" --provider example
```

Le ledger est append-only et hors Git.
