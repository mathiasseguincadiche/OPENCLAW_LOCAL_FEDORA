# Runbook d'exploitation Fedora

Ce runbook couvre l'exploitation quotidienne de `OPENCLAW_LOCAL_FEDORA`. Son objectif est de permettre à un opérateur de diagnostiquer, maintenir et restaurer la plateforme sans contourner les garde-fous de sécurité ni confondre santé logicielle et qualification matérielle.

## Principes opérateur

1. rester local-only pour le routage LLM nominal ;
2. préserver SELinux Enforcing et firewalld ;
3. utiliser `systemd --user` pour le Gateway OpenClaw ;
4. ne jamais modifier simultanément plusieurs variables lors d'un diagnostic de performance ;
5. sauvegarder avant réparation ou changement important ;
6. ne jamais déclarer un PASS matériel sans preuve produite sur la machine cible ;
7. préférer les commandes du dépôt aux manipulations manuelles non traçables.

## Routine rapide

Pour une vérification quotidienne :

```bash
cd OPENCLAW_LOCAL_FEDORA
./menu.sh --action health
```

Puis, si nécessaire :

```bash
openclaw gateway status
systemctl --user status openclaw-gateway.service --no-pager
ollama list
```

Si ces contrôles passent, le produit est généralement opérable. Cela ne constitue pas une requalification B580.

## État du Gateway OpenClaw

### Statut

```bash
openclaw gateway status
systemctl --user status openclaw-gateway.service --no-pager
```

### Logs

```bash
journalctl --user -u openclaw-gateway.service -n 200 --no-pager
```

Suivi en direct :

```bash
journalctl --user -u openclaw-gateway.service -f
```

### Redémarrage

```bash
systemctl --user restart openclaw-gateway.service
openclaw gateway status
```

Ne pas créer une seconde unité systemd concurrente pour le même Gateway.

## État d'Ollama

```bash
ollama --version
ollama list
systemctl status ollama.service --no-pager
```

Logs système :

```bash
journalctl -u ollama.service -n 200 --no-pager
```

Le service Ollama est distinct du Gateway OpenClaw. Une panne de l'un ne doit pas être diagnostiquée comme une panne de l'autre sans preuve.

## Vérification des modèles

L'inventaire nominal est défini dans `config/model_catalog.yaml`.

Contrôle opérateur :

```bash
ollama list
```

Si un modèle nominal manque, ne le télécharger que via le chemin explicite du produit :

```bash
./menu.sh --action models
./menu.sh --action models --apply
```

Aucun benchmark ne doit télécharger implicitement un modèle absent.

## Vérification des huit agents

```bash
./menu.sh --action health
```

Pour redéployer les workspaces gérés :

```bash
./menu.sh --action agents
```

Le redéploiement ne doit pas écraser un workspace étranger ou non marqué comme géré.

## Vérification de la B580

Diagnostic rapide :

```bash
lspci -Dnn | grep -Ei 'vga|display'
lsmod | grep '^xe '
ls -l /dev/dri
rpm -q mesa-vulkan-drivers
vulkaninfo --summary
```

La qualification formelle utilise :

```bash
./menu.sh --action hardware-l2
./menu.sh --action hardware-l3
```

Les résultats L2/L3 sont des preuves runtime. Ne pas les remplacer par une simple observation visuelle.

## SELinux

État :

```bash
getenforce
```

Le résultat nominal est `Enforcing`.

En cas de soupçon de blocage, inspecter les AVC au lieu de désactiver SELinux :

```bash
sudo ausearch -m AVC,USER_AVC -ts recent
```

ou, lorsque disponible :

```bash
sudo journalctl -t setroubleshoot --since '30 minutes ago'
```

Ne pas utiliser `setenforce 0` comme correction permanente ou comme moyen de faire passer un test.

## Firewalld et loopback

```bash
systemctl is-active firewalld
sudo firewall-cmd --state
```

Les providers modèles et le Gateway doivent rester conformes aux endpoints locaux définis par les contrats. Une ouverture réseau ne doit pas être ajoutée pour contourner un problème de configuration local.

## Stockage

Racine préférée :

```text
/srv/openclaw-local
```

Contrôles :

```bash
df -h /srv/openclaw-local
df -i /srv/openclaw-local
du -sh /srv/openclaw-local/* 2>/dev/null | sort -h
```

Répertoires à surveiller :

- `models/` ;
- `projects/` ;
- `proofs/` ;
- `benchmarks/` ;
- `backups/` ;
- `state/`.

Ne pas supprimer manuellement des preuves utilisées par un rapport L8 existant.

## Sauvegarde

Sauvegarde standard :

```bash
./menu.sh --action backup
```

Destination explicite :

```bash
./scripts/linux/12_backup_restore.sh backup --output-dir /chemin/backup
```

La sauvegarde couvre les données gérées prévues par le lifecycle et produit un manifeste avec hashes. Les poids modèles et le virtualenv sont reproductibles et ne constituent pas les données principales de sauvegarde.

## Restauration

La restauration exige une destination appropriée et suit les contrôles anti-traversal du produit :

```bash
./scripts/linux/12_backup_restore.sh restore ARCHIVE DESTINATION
```

Après restauration :

```bash
./menu.sh --action health
```

Ne pas restaurer au-dessus d'un état actif non compris. Préférer une destination vide puis valider avant bascule.

## Réparation

Dry-run :

```bash
./menu.sh --action repair
```

Application :

```bash
./menu.sh --action repair --apply
```

La réparation doit créer un backup avant de reconfigurer. Après réparation :

```bash
./menu.sh --action health
```

Si le problème persiste, passer au diagnostic par symptôme dans [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

## Désinstallation

Dry-run :

```bash
./menu.sh --action uninstall
```

Désinstallation conservatrice :

```bash
./menu.sh --action uninstall --apply
```

La purge des données est volontairement plus explicite :

```bash
./menu.sh --action uninstall --apply --purge-data
```

La purge destructive doit rester bornée par la racine runtime gérée et son marqueur.

## Vérification avant un changement

Avant un upgrade ou une campagne L6 :

```bash
./menu.sh --action health
./menu.sh --action backup
./menu.sh --action validate
```

Consulter ensuite [`UPGRADE.md`](UPGRADE.md).

## Parcours de qualification

Les commandes principales sont :

```bash
./menu.sh --action hardware-l2
./menu.sh --action hardware-l3
./menu.sh --action e2e --backend ollama-vulkan
./menu.sh --action qualification
./menu.sh --action golden
./menu.sh --action release-readiness
```

Ne pas enchaîner ces commandes comme un script aveugle. Lire [`QUALIFICATION.md`](QUALIFICATION.md), conserver les preuves et comprendre le gate qui a échoué avant de poursuivre.

## Collecte minimale pour un incident

Avant d'ouvrir une issue ou de demander une analyse, collecter sans secrets :

```bash
cat /etc/fedora-release
uname -r
getenforce
openclaw --version
ollama --version
openclaw gateway status
systemctl --user status openclaw-gateway.service --no-pager
systemctl status ollama.service --no-pager
ollama list
vulkaninfo --summary
```

Ajouter les extraits de logs pertinents, en supprimant secrets, tokens, prompts, réponses et contenus privés.

## Matrice d'escalade

| Symptôme | Première action |
|---|---|
| Gateway indisponible | `systemctl --user status` + journal utilisateur |
| Ollama indisponible | `systemctl status ollama.service` + journal système |
| modèle absent | `ollama list` puis provisionnement explicite |
| agent absent/incohérent | `health` puis `agents` |
| B580 invisible | `lspci`, `xe`, `/dev/dri`, `vulkaninfo` |
| AVC SELinux | `ausearch` / setroubleshoot |
| stockage plein | `df`, `du`, stratégie de rétention |
| config OpenClaw suspecte | dry-run `configure-openclaw` puis validation |
| qualification en échec | conserver la preuve, lire le gate concerné |
| upgrade à préparer | `UPGRADE.md`, une variable à la fois |

## Rollback

Le rollback dépend de la variable modifiée :

- configuration OpenClaw → réappliquer la baseline contractuelle ;
- runtime candidat → revenir à `ollama-vulkan` ;
- kernel candidat → booter le kernel Fedora officiel ;
- état applicatif → restaurer un backup validé ;
- version runtime → rétablir le pin précédent et revalider.

Un rollback doit être suivi de :

```bash
./menu.sh --action health
./menu.sh --action validate
```

et, si la variable touche la qualification, des gates concernés.

## Règle finale

L'objectif d'un runbook n'est pas de « faire passer » les checks ; il est d'établir l'état réel, appliquer une correction minimale, vérifier le résultat et conserver une voie de retour arrière.
