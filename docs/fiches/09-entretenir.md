# Entretenir

[← Guide](../GUIDE.md) · [Source de vérité et collecte](11-comment-ca-marche.md)

Le projet conserve tes sources et tes décisions : **sauvegarder** ne signifie pas encore **avoir testé une restauration**. Toute preuve de restauration doit venir d'un essai réel.

Avant toute opération de cette fiche, attends la fin d'une génération en cours ou mets ton projet en pause : ces commandes refusent de s'exécuter pendant que le modèle travaille.

## Sauvegarder

```bash
./menu.sh --action backup
```

La sauvegarde est rangée dans `/srv/openclaw-local/backups`. Elle contient l'état, les projets, les espaces de travail des rôles et tes conversations. Elle ne contient ni le modèle ni l'environnement Python : ils se retéléchargent.

Pour éviter les écritures pendant la sauvegarde, arrête d’abord les **quatre services de l’interface** : Open WebUI, son pont, la voix et le tableau de projets. Cette commande n’arrête pas à elle seule le Gateway OpenClaw ou Ollama ; vérifie qu’aucune génération n’est en cours :

```bash
./menu.sh --action webui-stop --apply
./menu.sh --action backup
./menu.sh --action webui-start --apply
```

Vers un autre disque :

```bash
scripts/linux/08_backup_restore.sh backup --output-dir /chemin/vers/le/disque
```

Les sauvegardes **ne sont pas chiffrées** : elles peuvent contenir tes conversations et les documents du projet. Protège l'archive comme des données confidentielles. Elles excluent la clé OpenRouter, le jeton de passerelle cloud, les jetons et la clé de session WebUI, le fichier `webui.env` ainsi que les codes d'approbation encore en attente. Après restauration, réinstalle WebUI pour régénérer ses secrets et sa configuration, puis ressaisis la clé OpenRouter (`cloud-set-key`). Le journal budgétaire reste sauvegardé pour conserver le plafond.

## Restaurer

```bash
scripts/linux/08_backup_restore.sh restore ARCHIVE DESTINATION
```

La destination doit être un dossier vide : la restauration n'écrase jamais des données existantes. Vérifie le contenu restauré avant de le mettre à la place de `/srv/openclaw-local`, puis relance `./menu.sh --action install --apply` et `./menu.sh --action health`.

## Vérification isolée facultative d'Open WebUI 0.12.3

La première installation choisit **Open WebUI 0.12.3** directement et
épingle par digest l'image téléchargée dans le service. Sur une machine
vierge, **aucune migration de 0.11.4 n'est nécessaire** et il n'est pas
obligatoire d'exécuter le canary avant l'installation.

Pour examiner la version en conteneur jetable et hors réseau :

```bash
bash scripts/linux/14_webui_canary.sh --apply
```

La commande `--with-db-copy` est réservée à l'étude d'une base SQLite
**déjà existante** et n'a aucun intérêt au premier déploiement. L'essai
automatisé ne remplace pas les tests navigateur, fichiers, fonctions et voix
sur le véritable PC Fedora.

## Mettre à niveau

Quand le dépôt passe à de nouvelles versions d'OpenClaw ou d'Ollama :

```bash
git pull
./menu.sh --action upgrade            # aperçu
./menu.sh --action upgrade --apply
```

La commande arrête les services, fait une sauvegarde, installe les versions prévues, réapplique la configuration, redémarre et vérifie avec une courte génération.

Si elle échoue, les services restent arrêtés et la sauvegarde est intacte. Pour revenir en arrière : reviens au commit précédent du dépôt (`git checkout <commit>`), restaure la sauvegarde dans un dossier vide, puis relance l'installation.

Refais ensuite la mesure du [premier essai](02-premier-essai.md) : une nouvelle version peut changer la vitesse.

Les mises à jour de Fedora (noyau, Mesa) passent par `dnf` comme d'habitude. Après une mise à jour de Mesa ou du noyau, lance `./menu.sh --action check-gpu`.

## Réparer

Si quelque chose est incohérent après une manipulation :

```bash
./menu.sh --action repair             # aperçu
./menu.sh --action repair --apply
```

La réparation sauvegarde, redépose les consignes des rôles, réapplique la configuration, redémarre OpenClaw et vérifie. Si le problème persiste, ne la relance pas en boucle : va à [Dépanner](10-depanner.md).

## Surveiller la place

```bash
df -h /srv/openclaw-local
du -sh /srv/openclaw-local/* | sort -h
```

Ce qui grossit : `backups/` (supprime les anciennes sauvegardes dont tu n'as plus besoin) et `projects/`.

## Désinstaller

```bash
./menu.sh --action uninstall                       # aperçu
./menu.sh --action uninstall --apply               # garde projets, modèle et sauvegardes
./menu.sh --action uninstall --apply --purge-data  # supprime aussi les données
```

La purge ne touche qu'au dossier `/srv/openclaw-local`.
