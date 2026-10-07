# Installer

[← Guide](../GUIDE.md)

## Ce qu'il faut avant de commencer

| Élément | Attendu | Vérifier |
|---|---|---|
| Système | Fedora 44 Workstation, GNOME, session Wayland | `cat /etc/fedora-release` et `echo "$XDG_SESSION_TYPE"` |
| Carte graphique | Intel Arc B580, pilote `xe` | `lspci \| grep -i vga` et `lsmod \| grep '^xe '` |
| BIOS | Démarrage UEFI, Resizable BAR activé | écran du BIOS |
| SELinux | `Enforcing` | `getenforce` |
| Pare-feu | actif | `systemctl is-active firewalld` |
| Place disque | au moins 15 Go libres pour le modèle et les outils | `df -h /srv` |

Lance l'installation depuis ton compte utilisateur habituel, jamais en root. Le script demande `sudo` seulement quand c'est nécessaire.

## Installer

```bash
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd OPENCLAW_LOCAL_FEDORA
./menu.sh --action validate           # vérifie les fichiers de configuration du dépôt
./menu.sh --action install            # affiche ce qui sera fait, sans rien modifier
./menu.sh --action install --apply
```

Après l'installation, ferme ta session et rouvre-la une fois : tu viens d'être ajouté aux groupes `render` et `video`, et ils ne s'appliquent qu'à une nouvelle session.

Pour ajouter le chat Open WebUI :

```bash
./menu.sh --action webui-install --apply
```

Ouvre `http://127.0.0.1:3000`, crée ton compte (il est local, aucun mail n'est envoyé), puis ferme les inscriptions :

```bash
./menu.sh --action webui-seal --apply
```

## Ce que fait l'installation, dans l'ordre

| Étape | Ce qui se passe | Relancer seule |
|---|---|---|
| 1. Préparation | Paquets Fedora (Vulkan, outils de contrôle), dossier `/srv/openclaw-local`, environnement Python | `./menu.sh --action bootstrap --apply` |
| 2. Ollama | Installation de la version prévue, configuration du service pour utiliser la B580 en Vulkan | — |
| 3. OpenClaw | Installation de la version exacte prévue | — |
| 4. Modèle | Téléchargement de Qwen 3.5 9B (environ 6,6 Go) et enregistrement de son empreinte | `./menu.sh --action models --apply` |
| 5. Rôles | Dépôt des consignes des sept rôles dans leurs espaces de travail | `./menu.sh --action agents` |
| 6. Configuration | Application de la configuration OpenClaw générée par le dépôt | `./menu.sh --action configure-openclaw --apply` |
| 7. Service | Démarrage du Gateway OpenClaw comme service de ton compte | — |
| 8. Vérification | Contrôle de santé avec une courte génération | `./menu.sh --action health` |

Les versions installées sont écrites dans `config/runtime_versions.yaml`. L'installation refuse de continuer si une autre version est présente : voir [Réglages](08-reglages.md) pour en changer volontairement.

## Où sont rangées les données

```text
/srv/openclaw-local/
├── models/       le modèle Qwen
├── workspaces/   un espace de travail par rôle
├── projects/     tes projets de l'atelier
├── state/        configuration et conversations
├── backups/      sauvegardes
├── proofs/       rapports des contrôles matériels
└── runtime/      environnement Python et fichiers générés
```

Rien de tout cela n'est dans Git. Le dépôt contient le code et la configuration ; ce dossier contient tes données.

## Ce que l'installation ne fait pas

- Elle n'ouvre aucun port sur le réseau : tout écoute sur `127.0.0.1`, donc uniquement depuis ton PC.
- Elle ne désactive ni SELinux ni le pare-feu.
- Elle ne touche pas au noyau.
- Elle ne garde pas les services actifs quand ta session est fermée, sauf si tu ajoutes `--enable-linger` à `scripts/linux/06_install.sh`.

## Ensuite

Passe au [premier essai](02-premier-essai.md) : c'est lui qui dit si la carte graphique travaille et à quelle vitesse.
