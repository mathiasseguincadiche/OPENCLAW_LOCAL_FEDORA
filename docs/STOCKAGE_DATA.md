# Stockage sur le SSD secondaire `/data`

La configuration de référence est [config/storage.json](../config/storage.json) :
montage **EXT4** sous `/data`, données sous `/data/IA/Openclaw`.
Le deuxième Crucial T705 peut conserver simultanément :

```text
/data/
├── Documents/
├── Projets/
├── ISO/
├── Jeux/
├── IA/Openclaw/
│   ├── sources/OPENCLAW_LOCAL_FEDORA/
│   ├── models/                 # Ollama et transcription
│   ├── projects/               # projets internes de l’atelier
│   ├── workspaces/             # espaces des sept rôles
│   ├── state/                  # OpenClaw, conversations et données WebUI
│   ├── runtime/venv/
│   ├── runtime/podman/storage/ # images et couches du conteneur WebUI
│   ├── proofs/
│   └── backups/
└── libvirt/
```

Les scripts ne déplacent pas les autres dossiers de `/data` et ne préparent pas
le partitionnement. **Ne pas reformater un volume contenant des données.**
Le dossier `/data/Projets` reste disponible pour tes dépôts Git et travaux DevOps ;
les projets internes de l’atelier et leurs copies importées ont leur propre dossier.

## Avant la première installation

Configurer le montage permanent par UUID dans GNOME Disks, puis contrôler :

```bash
findmnt --mountpoint /data -o TARGET,SOURCE,FSTYPE,OPTIONS,UUID
df -h /data /
```

Vérifier qu’il s’agit du deuxième SSD, en EXT4, accessible en lecture/écriture,
avec exécution autorisée. Le pré-check refuse le même système de fichiers que `/`,
les liens symboliques dans les parents et dossiers sensibles, un montage `ro`
ou `noexec`, et les dossiers gérés redirigés vers un autre volume.
Il vérifie au moins **15 GiB libres sur `/data`** et **8 GiB sur le SSD système**.
Ces seuils sont des minimums de départ ; prévoir de la marge pour les projets,
les mises à jour, les images et les sauvegardes.

Pour vérifier aussi l’identité du disque, recopier son UUID observé et confirmé
dans le champ `volume_uuid` de `config/storage.json`. Un champ vide vérifie le
montage et ses propriétés, mais ne prouve pas l’identité physique du SSD.
Le contrôle ne formate, ne monte et ne modifie jamais le volume.

Les valeurs par défaut fonctionnent sans fichier `.env`. `.env.example` est un
exemple documentaire, **pas un fichier exécuté ou chargé automatiquement**.
Un autre montage nécessite deux valeurs cohérentes, exportées dans le terminal :

```bash
export OPENCLAW_LOCAL_FEDORA_MOUNT=/autre-volume
export OPENCLAW_LOCAL_FEDORA_ROOT=/autre-volume/IA/Openclaw
```

La racine doit être strictement sous le montage déclaré. Les services générés
conservent ces deux valeurs. Changer de chemin n’effectue aucune migration des
données existantes ; préparer une sauvegarde et examiner l’ancienne installation
avant de modifier sa configuration.

## Permissions et SELinux

Le bootstrap crée uniquement la racine de l’atelier et ses sous-dossiers, avec
des permissions privées. Il ne change pas récursivement les propriétaires de
`/data`, `Documents`, `Jeux` ou `libvirt`.

Le compte de service Ollama reçoit une ACL de traversée sur les parents de son
dossier de modèles, jusqu’au montage déclaré. Cette permission lui permet
d’atteindre `models/ollama` sans lui donner la lecture des projets ni des secrets.
Son répertoire de modèles appartient au compte Ollama ; son service reçoit les
groupes GPU `render` et `video`.

SELinux doit rester **Enforcing**. Open WebUI conserve le montage privé de ses
données avec l’option `:Z`. Le stockage Podman dédié reçoit une équivalence de
contexte SELinux limitée à `runtime/podman`, suivie de `restorecon`. La réception
sur le vrai Fedora doit encore vérifier les accès et les éventuels refus SELinux.

## Open WebUI et les autres conteneurs

L’installation produit `runtime/generated/webui-storage.conf`. Seuls les appels
Podman de l’atelier et son service utilisent cette configuration via
`CONTAINERS_STORAGE_CONF`. Les images et couches sont stockées dans
`runtime/podman/storage`, les téléchargements temporaires sous `runtime/podman/tmp`,
et les données transitoires de fonctionnement sous `/run/user/UID/`.

La configuration personnelle `~/.config/containers/storage.conf` et le stockage
des autres conteneurs ne sont pas remplacés. Les appels gérés imposent le mode
local de Podman. Une ancienne image située dans le stockage personnel n’est pas
migrée automatiquement. Le canary utilise le même stockage dédié, avec un
conteneur et une copie des données séparés.

Les paquets système et le binaire Ollama restent sur le SSD système ; OpenClaw
et Parallel restent sous `~/.openclaw`. Les scripts ne déplacent pas les logiciels
Fedora. Le dépôt Git doit rester à un chemin stable car Python est installé en
mode éditable depuis ses sources.

Références : [configuration de stockage officielle](https://github.com/containers/storage/blob/main/docs/containers-storage.conf.5.md),
[documentation Podman](https://docs.podman.io/en/stable/markdown/podman.1.html).

## Sauvegarde et restauration

La commande de sauvegarde habituelle utilise `backups/`, sur le même SSD. Elle
protège contre certaines erreurs de manipulation, pas contre la perte du disque.
Copier régulièrement une archive sur un support externe protégé, puis tester sa
restauration dans un dossier vide. Voir [la procédure complète](fiches/09-entretenir.md).

Conserver aussi les réglages locaux (UUID et chemins) avant de réinstaller.

Les modèles, l’environnement Python, les sources Git et les couches Podman ne
font pas partie de la sauvegarde des données : conserver la référence Git et
réinstaller les composants prévus. Les sauvegardes ne sont pas chiffrées et
certains secrets sont exclus ; suivre la procédure de régénération des secrets.

Après installation, exécuter `quick-check`, essayer réellement Open WebUI et
effectuer une restauration isolée. La réception près de 32K reste un contrôle
distinct sur la B580 ; aucun de ces essais ne dépense de crédit cloud.
