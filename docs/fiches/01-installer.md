# Installer

[← Guide](../GUIDE.md) · [Architecture expliquée](11-comment-ca-marche.md)

Pour découvrir **ce que tu installes** avant de lancer les scripts, consulte le schéma des composants et le rôle d'OpenClaw/Ollama.

## Ce qu'il faut avant de commencer

| Élément | Attendu | Vérifier |
|---|---|---|
| Système | Fedora 45 Workstation stable publiée, GNOME 51, session Wayland | `cat /etc/fedora-release`, `gnome-shell --version` et `echo "$XDG_SESSION_TYPE"` |
| Carte graphique | Intel Arc B580, pilote `xe` | `lspci \| grep -i vga` et `lsmod \| grep '^xe '` |
| BIOS | Démarrage UEFI, Resizable BAR activé | écran du BIOS |
| SELinux | `Enforcing` | `getenforce` |
| Pare-feu | actif | `systemctl is-active firewalld` |
| Place disque | au moins 15 Go libres pour le modèle et les outils | `findmnt --mountpoint /data && df -h /data` |

Lance l'installation depuis ton compte utilisateur habituel, jamais en root. Le script demande `sudo` seulement quand c'est nécessaire.

Utiliser une image **stable officiellement publiée** de Fedora 45 Workstation ; ne pas confondre une image bêta et le système hôte cible du dépôt. Une installation réelle sur le PC reste à réceptionner. Fedora 44 et GNOME 50 sont volontairement refusés lors de l'installation ; aucune installation/migration depuis Fedora 44 n'est nécessaire.

> **Parcours court recommandé :** [Fedora installé, stockage `/data/IA/Openclaw`, installation et un seul `quick-check`](../INSTALLATION_SIMPLE_FEDORA45.md). Le reste de cette fiche détaille les étapes facultatives de dépannage.

## Installer

```bash
# Git peut ne pas être présent sur un Fedora tout juste installé.
command -v git >/dev/null 2>&1 || sudo dnf5 install -y git
# Chaque étape dépend du contrôle du vrai volume secondaire.
mountpoint -q /data &&
  test "$(stat -c '%d' /data)" != "$(stat -c '%d' /)" &&
  sudo install -d -m 0750 -o "$(id -un)" -g "$(id -gn)" /data/IA/Openclaw/sources &&
  git -C /data/IA/Openclaw/sources clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd "/data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA"
./menu.sh --action precheck           # vérifie OS, machine, disque et dépendances sans modification
./menu.sh --action install            # affiche le plan, sans vérification complète
./menu.sh --action install --apply    # installe et contrôle les vrais prérequis
./menu.sh --action validate           # après le bootstrap Python et ses dépendances
```

Lancer ces commandes **après** la vérification du montage `/data` dans le [guide court](../INSTALLATION_SIMPLE_FEDORA45.md). Ne pas exécuter `validate` avant le bootstrap sur un Fedora vierge : ce contrôle importe notamment PyYAML, qui n'est pas garanti avant l'installation du venv. Le pré-check refuse les prérequis bloquants, mais les paquets encore absents sont simplement signalés et installés lors du bootstrap. Le même contrôle est imposé par `install --apply` avant toute installation de dépendance. L'aperçu `install` seul ne prouve pas la compatibilité B580 ; le `--apply` et le `quick-check` final la vérifient à des niveaux différents.

Après l'installation, ferme ta session et rouvre-la une fois : tu viens d'être ajouté aux groupes `render` et `video`, et ils ne s'appliquent qu'à une nouvelle session.

Pour ajouter le chat Open WebUI **dans un nouveau terminal après la reconnexion** :

```bash
cd "/data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA"
./menu.sh --action webui-install --apply
```

Ouvre `http://127.0.0.1:3000`, crée ton compte (il est local, aucun mail n'est envoyé), puis ferme les inscriptions :

```bash
./menu.sh --action webui-seal --apply
```

## Ce que fait l'installation, dans l'ordre

| Étape | Ce qui se passe | Relancer seule |
|---|---|---|
| 1. Préparation | Paquets Fedora (Vulkan, outils de contrôle), dossier `/data/IA/Openclaw`, environnement Python | `./menu.sh --action bootstrap --apply` |
| 2. Ollama | Installation de la version prévue, configuration du service pour utiliser la B580 en Vulkan | — |
| 3. OpenClaw | Installation de la version exacte prévue | — |
| 4. Modèle | Téléchargement de Qwen 3.5 9B (environ 6,6 Go) et enregistrement de son empreinte | `./menu.sh --action models --apply` |
| 5. Rôles | Dépôt des consignes des sept rôles dans leurs espaces de travail | `./menu.sh --action agents` |
| 6. Configuration | Application de la configuration OpenClaw générée par le dépôt | `./menu.sh --action configure-openclaw --apply` |
| 7. Service | Démarrage du Gateway OpenClaw comme service de ton compte | — |
| 8. Vérification | Contrôle de santé avec une courte génération | `./menu.sh --action quick-check` |

Les versions installées sont écrites dans `config/runtime_versions.yaml`. L'installation refuse de continuer si une autre version est présente : voir [Réglages](08-reglages.md) pour en changer volontairement.

## Où sont rangées les données

```text
/data/IA/Openclaw/
├── sources/      dépôt Git et code source de l'atelier
├── models/       le modèle Qwen
├── workspaces/   un espace de travail par rôle
├── projects/     tes projets de l'atelier
├── state/        configuration, conversations, et état du cloud (state/cloud, state/project-cloud)
├── backups/      sauvegardes
├── proofs/       rapports des contrôles matériels
└── runtime/      environnement Python et fichiers générés
```

Seul le dépôt dans `sources/OPENCLAW_LOCAL_FEDORA` est suivi par Git. Les modèles,
projets, conversations et autres données du runtime restent en dehors de ce dépôt.

## Ce que l'installation ne fait pas

- Elle n'active pas le cloud et ne demande aucune clé : c'est une étape séparée et facultative ([Le cloud, facultatif](12-cloud.md)).
- Elle n'ouvre aucun port sur le réseau : tout écoute sur `127.0.0.1`, donc uniquement depuis ton PC.
- Elle ne désactive ni SELinux ni le pare-feu.
- Elle ne touche pas au noyau.
- Elle ne garde pas les services de ton compte actifs après fermeture de session par défaut. Pour un service actif hors session, le *lingering* est un choix explicite de configuration utilisateur (`sudo loginctl enable-linger "$USER"`), non activé par le parcours court ; inutile pour la première réception.

## Ensuite

Lance **`./menu.sh --action quick-check`**. Si le résultat est `READY_FOR_FIRST_PROJECT`, ouvre Open WebUI, pose une question réelle et crée ton premier projet.

Pour mesurer ensuite la capacité 32K de la B580, tu peux lancer **`./menu.sh --action acceptance-32k --apply`** : ce test local, potentiellement long, est **facultatif pour commencer à travailler**. Un `quick-check` réussi ne certifie pas 32 768 tokens. Le protocole 32K et les autres diagnostics sont détaillés dans [Premier essai](02-premier-essai.md).
