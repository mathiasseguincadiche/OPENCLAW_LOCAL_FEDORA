# Installation simple — Fedora 45 et atelier IA

## Choix retenu

Fedora 45 Workstation / GNOME 51 est installé **normalement sur le SSD système**.
Le Python 3.15 du système n'est pas modifié : l'atelier utilise un venv isolé
en **Python 3.13** (fourni par Fedora) pour rester compatible avec la voix.
Le deuxième disque, formaté en système de fichiers Linux (ext4, Btrfs ou XFS), est
monté au démarrage sous **`/IA`**. L'atelier utilise **`/IA/Openclaw/`**.
Pas de clé Live ni de benchmarks longs imposés.

## 1. Préparer le deuxième disque une seule fois

Ouvrir **Disques (GNOME Disks)** et identifier le deuxième disque par
sa **capacité et son modèle**, pas uniquement par `/dev/nvme...` (l'ordre change).
S'il contient des données, les sauvegarder : **ne pas reformater**.
Dans les options de montage, configurer le volume par **UUID** pour qu'il
soit monté automatiquement sur `/IA` à chaque démarrage. Créer le dossier
`/IA` si nécessaire ; un montage déjà présent ailleurs devra être ajusté
manuellement dans GNOME Disks. Ne pas copier de commande de formatage.

Contrôle impératif avant installation :

```bash
findmnt --mountpoint /IA
df -h /IA
```

Le résultat doit décrire le **deuxième disque** et pas `/`.
Le programme refuse de poursuivre si `/IA` n'est pas monté ou si le
point de montage correspond au même système de fichiers que `/`.
Il refuse également les chemins avec traversée `..` ou liens symboliques,
ainsi que les redirections par liens dans les répertoires sensibles
(`models`, `projects`, `state`, `runtime`, `backups`, etc.). **Ne pas utiliser
un lien symbolique pour déplacer une partie des données hors de `/IA`.**
On ne lance aucun script d'installation avant ce contrôle.

## 2. Installer l'atelier

Dans un terminal de la session **GNOME 51 Wayland**, avant le clonage :

```bash
cat /etc/fedora-release
gnome-shell --version
printf 'Session : %s\n' "${XDG_SESSION_TYPE:-inconnue}"
getenforce
```

Attendus : Fedora 45 Workstation stable, GNOME Shell 51, session `wayland`, SELinux `Enforcing`. Si l'un manque, corriger l'environnement avant de lancer le script. Le contrôle du montage `/IA` de l'étape 1 est obligatoire ; l'aperçu d'installation seul **ne vérifie pas le GPU ni tous les prérequis**.

Dans le terminal Fedora (compte normal, pas root), installer `git` **seulement s'il est absent**, puis cloner le dépôt dans le dossier personnel :

```bash
command -v git >/dev/null 2>&1 || sudo dnf5 install -y git
cd "$HOME"
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd "$HOME/OPENCLAW_LOCAL_FEDORA"
./menu.sh --action install        # plan seulement ; ne certifie pas la compatibilité matérielle
./menu.sh --action install --apply
```

**Ne pas lancer directement les scripts du répertoire `scripts/linux/` :** le lanceur `menu.sh` sélectionne la procédure et propage `--apply` au bon script. Ne pas recopier `git clone` si le dépôt existe déjà ; ouvrir son dossier. Les opérations de préparation peuvent demander le mot de passe `sudo`, télécharger plusieurs Go et nécessitent une connexion Internet. L'installateur ne reformate aucun disque, n'active pas DeepSeek et ne remplace pas ton Python système.

Le bootstrap vérifie le second disque avant d'installer des paquets.
Il crée `/IA/Openclaw` et ses répertoires, installe les versions épinglées
d'Ollama/OpenClaw, le modèle Qwen local, les sept agents et le Gateway.
Le téléchargement du modèle et des logiciels demande Internet.

**Déconnecter puis reconnecter la session GNOME** pour prendre en compte
les groupes GPU `render` et `video`.

Après reconnexion, le nouveau terminal revient normalement dans ton dossier personnel. **Revenir explicitement dans le dépôt** avant d'appeler `./menu.sh` :

```bash
cd "$HOME/OPENCLAW_LOCAL_FEDORA"
./menu.sh --action webui-install --apply
```

Ouvrir `http://127.0.0.1:3000`, créer l'unique compte local puis fermer
les inscriptions :

```bash
./menu.sh --action webui-seal --apply
```

## 3. Un seul contrôle rapide

```bash
./menu.sh --action quick-check
```

Ce contrôle ne lance **qu'une petite génération Qwen locale**, vérifie
que la B580 utilise de la VRAM, la version du modèle, OpenClaw, Ollama,
le réseau local des interfaces WebUI/Projets, SELinux et le répertoire projets.
Il affiche les composants en `PASS` ou `FAIL` puis un verdict final.

Si `RECEPTION=READY_FOR_FIRST_PROJECT`, ouvrir :

- Discussions : `http://127.0.0.1:3000` ;
- Atelier Projets : `http://127.0.0.1:18890`.

Poser une question réelle sur Terraform ou Ansible ; créer un petit projet
de test puis changer de projet avec la commande de navigation.
Il n'est **pas nécessaire** de lancer immédiatement des essais 32K,
cinq veilles/réveils ou les sept scénarios d'évaluation.
Ces tests complémentaires sont disponibles **si une anomalie apparaît** ou
si l'on veut mesurer des performances plus finement.

Le cloud DeepSeek n'est **pas activé automatiquement**. Un appel réel
nécessite une clé et une activation explicites ; aucun test de cloud
ne peut être déclaré réussi sans cet accord. Après la réception locale,
utiliser [la fiche Cloud](fiches/12-cloud.md#activer-le-cloud) pour la saisie
masquée de la clé OpenRouter, la limite en dollars et l'activation consentie.

## Stockage exact

```text
/IA/Openclaw/
├── models/ollama/     Modèle Qwen et autres téléchargements Ollama
├── projects/          Projet 1, Projet 2, Projet 3, Projet 4…
├── workspaces/        Espace de travail de chaque agent
├── state/openclaw/    Configuration et état OpenClaw
├── state/webui/data/  Base et paramètres Open WebUI
├── state/cloud/       Paramètres locaux de la passerelle cloud
├── runtime/venv/      Python isolé du projet
├── runtime/generated/ Configurations générées
├── proofs/            Rapports
└── backups/           Archives de sauvegarde
```

**Exceptions légères et normales :** Fedora conserve les unités systemd,
Ollama `/usr/local/bin/ollama`, le lanceur npm OpenClaw dans
`~/.openclaw/` et la configuration du compte dans son dossier personnel.
Les fichiers volumineux et données de projets restent sur le second disque.
Le code Git cloné dans `~/OPENCLAW_LOCAL_FEDORA` reste sur le système
tant que l'opérateur ne le déplace pas volontairement.

Les unités systemd gérées empêchent le démarrage si `/IA` n'est plus un
point de montage. Ne pas le démonter pendant un projet ou une génération.
Les sauvegardes du dossier `backups/` sont **sur le même disque** :
en prévoir aussi une copie externe en cas de panne du second disque.

## En cas d'échec

Un `FAIL` permet de cibler la correction. **Ne pas tout réinstaller**.
Contrôler d'abord `findmnt --mountpoint /IA`, puis
`./menu.sh --action health` pour le rapport détaillé.
Le protocole complet reste disponible dans
`docs/QUALIFICATION_FINALE_FEDORA.md`, sans être obligatoire au premier usage.
