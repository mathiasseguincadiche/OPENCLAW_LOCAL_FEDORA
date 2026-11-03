# Réception de l'atelier sur le PC — liste de contrôle (étape 3)

[← Documentation](README.md) · [Installation simple](INSTALLATION_SIMPLE_FEDORA45.md) · [Dépannage](fiches/10-depanner.md) · [État du projet](../STATUS.md)

**But :** prouver, sur la vraie machine (Ryzen 7 7700, 48 Go, Arc B580 12 Go), que l'atelier s'installe, répond en local, mène un projet jusqu'à la livraison, survit à une sauvegarde et à un redémarrage, puis, si tu le décides, appelle le cloud dans le budget prévu. Une CI verte ne prouve aucun de ces points ; seule cette campagne le peut.

**Mode d'emploi :**

- Coche chaque case quand le résultat **attendu** est obtenu.
- Au premier écart, **arrête-toi** : note la phase, la commande et les dernières lignes affichées, puis applique la colonne « Si ça échoue ». **Ne réinstalle pas tout.**
- Compte environ 3 h pour les phases 1 à 9, plus 30 min pour le cloud (phase 10). On peut s'arrêter à la fin de n'importe quelle phase et reprendre plus tard.
- **Ne recopie jamais** une clé OpenRouter, un mot de passe ou un jeton dans un rapport, une capture ou un message.

Dans toutes les commandes, le dépôt est **`/data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA`**. Après une reconnexion ou dans un nouveau terminal, y revenir d'abord :

```bash
cd /data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA
```

## Phase 0 — Avant le jour J

- [ ] **Fedora 45 est officiellement publiée** : l'ISO Workstation finale est disponible sur [fedoraproject.org](https://fedoraproject.org/fr/workstation/download). Ne pas utiliser une bêta.
- [ ] La somme de contrôle de l'ISO est vérifiée selon la page de téléchargement.
- [ ] Les données éventuellement présentes sur le **deuxième SSD** sont sauvegardées ailleurs. L'installation ne le formate pas, mais une erreur de disque dans l'installateur Fedora reste possible.
- [ ] Dans l'UEFI : démarrage UEFI, **Resizable BAR / Above 4G decoding activés** (recommandé pour la B580), Secure Boot selon ton choix (pris en charge).
- [ ] Une connexion Internet stable : plusieurs Go à télécharger (paquets, Ollama, OpenClaw, modèle Qwen d'environ 6 Go, image Open WebUI).
- [ ] Facultatif, pour la phase 10 : un compte OpenRouter. Rien n'est à acheter tant que tu n'as pas décidé d'essayer le cloud.

Le contrôle Live USB ([guide](LIVE_USB_FEDORA45_PREQUALIFICATION.md)) est **facultatif** : il observe seulement le matériel. La phase 1 refait les vérifications utiles sur le système installé.

## Phase 1 — Fedora installée sur le SSD système

Installer Fedora 45 Workstation normalement **sur le SSD système uniquement**, créer ton compte (administrateur), puis mettre à jour et redémarrer :

```bash
sudo dnf upgrade --refresh
```

```bash
systemctl reboot
```

Puis vérifier, dans un terminal de la session graphique :

```bash
cat /etc/fedora-release
gnome-shell --version
printf 'Session : %s\n' "${XDG_SESSION_TYPE:-inconnue}"
getenforce
lspci -k | grep -EA3 'VGA|Display'
ls /dev/dri
```

| Attendu | Si ça échoue |
| --- | --- |
| [ ] `Fedora release 45` (pas de mention Beta) | Attendre l'ISO finale ; ne pas continuer sur une préversion |
| [ ] `GNOME Shell 51.x` | Le bootstrap refusera de continuer : vérifier l'édition Workstation |
| [ ] `Session : wayland` | Se déconnecter et choisir la session GNOME standard (Wayland) |
| [ ] `Enforcing` | Ne pas désactiver SELinux : le signaler, l'atelier exige Enforcing |
| [ ] La B580 apparaît avec `Kernel driver in use: xe` | Vérifier ReBAR et le firmware ; ne pas installer de pilote tiers |
| [ ] `/dev/dri` contient un `renderD…` | Même diagnostic que la ligne précédente |

## Phase 2 — Le deuxième SSD monté sur `/data`

Avec **Disques (GNOME Disks)**, identifier le deuxième SSD par sa **capacité et son modèle**. S'il n'est pas déjà formaté en EXT4, le formater en EXT4 **seulement s'il est vide ou sauvegardé**. Dans les options de montage, choisir le montage automatique au démarrage par **UUID** sur `/data`. Détail : [Installation simple, étape 1](INSTALLATION_SIMPLE_FEDORA45.md#1-préparer-le-deuxième-disque-une-seule-fois).

```bash
findmnt --mountpoint /data
df -h /data
test "$(stat -c '%d' /data)" != "$(stat -c '%d' /)" && echo "OK : disque distinct"
```

| Attendu | Si ça échoue |
| --- | --- |
| [ ] `findmnt` montre le deuxième SSD, type `ext4` | Revoir le montage dans GNOME Disks : point de montage `/data`, montage au démarrage |
| [ ] `OK : disque distinct` | `/data` est un simple dossier du disque système : refaire le montage |
| [ ] Après un **redémarrage**, `findmnt --mountpoint /data` affiche toujours le SSD | L'option de montage au démarrage n'est pas enregistrée |

## Phase 3 — Récupérer le dépôt et faire le pré-contrôle

```bash
command -v git >/dev/null 2>&1 || sudo dnf5 install -y git
sudo install -d -m 0750 -o "$(id -un)" -g "$(id -gn)" /data/IA/Openclaw/sources
git -C /data/IA/Openclaw/sources clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
```

```bash
cd /data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA
./menu.sh --action precheck
```

| Attendu | Si ça échoue |
| --- | --- |
| [ ] `PRECHECK=READY_TO_INSTALL` | `PRECHECK=BLOCKED` : corriger chaque ligne `FAIL` avant de continuer. Les lignes `REVIEW` (paquets à installer, ReBAR, mesures GPU) sont normales à ce stade |

## Phase 4 — Installer l'atelier

```bash
./menu.sh --action install
```

```bash
./menu.sh --action install --apply
```

La première commande n'affiche que le plan ; la seconde installe. Elle demande le mot de passe `sudo` et dure longtemps : téléchargement du modèle Qwen.

| Attendu | Si ça échoue |
| --- | --- |
| [ ] Une ligne `NODE_ENGINE_RESULT=PASS node=v24…` | Fedora 45 fournit Node 22 par défaut et le script installe `nodejs24`. Si `dnf` signale un **conflit avec le paquet `nodejs`**, s'arrêter et noter le message exact, sans forcer la suppression |
| [ ] `INSTALL_RESULT=PASS`, puis `OLLAMA_VERSION=0.40.6` et `OPENCLAW_VERSION=2026.10.5` | Noter la dernière ligne `FAIL` ; relancer seulement après correction de la cause |

Ensuite, **se déconnecter puis se reconnecter** à la session GNOME, pour les groupes `render`/`video`. Dans un **nouveau terminal** (son PATH ne contient pas `~/.openclaw/bin`) :

```bash
cd /data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA
./menu.sh --action health
```

| Attendu | Si ça échoue |
| --- | --- |
| [ ] `openclaw-cli` en `PASS`, avec le chemin `~/.openclaw/bin/openclaw`, même dans ce terminal neuf | Le CLI n'a pas été installé : revoir la sortie de la phase 4 |
| [ ] `ollama`, `openclaw-gateway`, `agent-workspaces` (`7 managed`) et `model-inventory` en `PASS` | Lire la ligne `FAIL` ; ne pas réinstaller, appliquer la [fiche Dépannage](fiches/10-depanner.md) |

## Phase 5 — Le chat Open WebUI

```bash
./menu.sh --action webui-install --apply
```

Ouvrir `http://127.0.0.1:3000`, créer **l'unique compte** local, puis fermer les inscriptions :

```bash
./menu.sh --action webui-seal --apply
./menu.sh --action webui-status
```

| Attendu | Si ça échoue |
| --- | --- |
| [ ] La page de WebUI s'ouvre et le compte est créé | `webui-status` ; vérifier que `/data` est monté |
| [ ] Après `webui-seal`, une fenêtre privée ne propose plus de créer de compte | Relancer `webui-seal --apply` et noter la sortie |
| [ ] Les **sept rôles** apparaissent dans la liste des modèles | `./menu.sh --action health` |

## Phase 6 — Le contrôle rapide

```bash
./menu.sh --action quick-check
```

| Attendu | Si ça échoue |
| --- | --- |
| [ ] `RECEPTION=READY_FOR_FIRST_PROJECT` | Chaque composant affiche `PASS` ou `FAIL` : corriger le premier `FAIL` |
| [ ] La ligne `PASS model-gpu-probe` est présente | Le modèle ne tourne pas sur la B580 : revoir la phase 1 (pilote `xe`, `/dev/dri`) et noter la sortie de `./menu.sh --action check-gpu` |

Juste après le contrôle, tant que le modèle est encore chargé :

```bash
ollama ps
```

- [ ] La colonne `PROCESSOR` indique **`100% GPU`**. Une part CPU signifie que le modèle ou son contexte ne tient pas entièrement sur la carte.

**À noter :** la taille affichée par `ollama ps` (mémoire vidéo occupée).

## Phase 7 — Discuter en local

Dans WebUI, choisir un rôle **local**, par exemple le mentor (`chef-operations`), puis :

- [ ] Poser une vraie question : « Explique-moi la différence entre `terraform plan` et `terraform apply`, avec un exemple. » La réponse arrive en local, sans bandeau ☁️.
- [ ] Joindre un **petit fichier** texte ou YAML et demander de l'expliquer. Le contenu est bien lu.
- [ ] Pendant une réponse, ouvrir `http://127.0.0.1:18890` (Atelier Projets). L'activité indique un traitement en cours, puis revient au repos.

**À noter :** le temps de la première réponse (chargement du modèle) et celui des suivantes.

## Phase 8 — Un premier projet jusqu'à la livraison

Dans une nouvelle conversation, suivre le parcours de la [réception WebUI, section 3](SMOKE_TEST_WEBUI.md#3-commandes-projet-de-bout-en-bout) :

1. `!creer essai-reception`, puis taper la phrase de confirmation ;
2. `!projet essai-reception` et joindre un petit `README.md` ;
3. `!analyser` puis approuver ; `!planifier` puis `!valider` ;
4. `!lancer` puis suivre avec `!etat` ;
5. `!auditer`, puis `!relire` ;
6. **ne pas encore livrer.**

- [ ] Les mêmes états et livrables apparaissent dans l'Atelier Projets (`http://127.0.0.1:18890`).
- [ ] **Accord cloud lié au bon projet (A03)** : créer un second petit projet, puis ouvrir rapidement l'un puis l'autre dans l'Atelier. Le panneau « Cloud pour ce projet » affiche toujours le nom du projet ouvert. *Ne rien autoriser.*
- [ ] **Livrable modifié après l'audit (A05)** : ouvrir un fichier sous `/data/IA/Openclaw/projects/essai-reception/deliverables/`, y ajouter une ligne et enregistrer, puis tenter `!livrer`. La livraison est **refusée** avec « audit périmé ».
- [ ] Remettre le fichier dans son état d'origine, ou demander une reprise avec `!modifier <tâche> <raison>`, refaire les audits puis `!livrer` et confirmer. L'état final est `COMPLETE` et le PDF, le DOCX ou l'ODT livré s'ouvre correctement.

## Phase 9 — Sauvegarde, redémarrage, mode jeu

**Sauvegarde refusée pendant une génération (A04) :** lancer une longue question dans le chat, puis, **pendant qu'elle tourne** :

```bash
./menu.sh --action backup
```

- [ ] `BACKUP_RESULT=REFUSED` : la sauvegarde attend la fin de la génération.

Puis, quand rien ne tourne :

```bash
./menu.sh --action backup
ls -lh /data/IA/Openclaw/backups/
```

- [ ] `BACKUP_RESULT=PASS` et une archive `openclaw-local-fedora-….tar.gz` présente.

Vérifier l'archive : la commande restaure une copie temporaire, contrôle les empreintes et la supprime.

```bash
/data/IA/Openclaw/runtime/venv/bin/clawfedora-backup-verify /data/IA/Openclaw/backups/NOM_DE_L_ARCHIVE.tar.gz
```

- [ ] Le résultat est favorable.
- [ ] **Copier l'archive hors du deuxième SSD** (clé USB, autre disque) : les sauvegardes de `backups/` sont sur le même disque que les données.

**Redémarrage complet :**

```bash
systemctl reboot
```

Après reconnexion :

```bash
cd /data/IA/Openclaw/sources/OPENCLAW_LOCAL_FEDORA
./menu.sh --action quick-check
```

- [ ] `RECEPTION=READY_FOR_FIRST_PROJECT` à nouveau, et l'ancien projet est toujours visible dans l'Atelier.

**Mode jeu, pour libérer la B580 :**

```bash
./menu.sh --action gaming --apply
./menu.sh --action daily --apply
```

- [ ] En mode jeu, `ollama ps` ne répond plus (service arrêté) et le chat refuse de générer (« mode jeux actif ») ; en mode quotidien, il répond de nouveau.

## Phase 10 — Le cloud, borné (facultatif)

**Chez OpenRouter, toi-même :**

- [ ] Paramètres de confidentialité restrictifs : refuser les fournisseurs qui conservent tes données ou s'en servent pour l'entraînement.
- [ ] Crédits **prépayés**, rechargement automatique **désactivé**, montant inférieur à 25 €.
- [ ] Une clé API avec une **limite de 12 $**.

**Sur le PC :**

```bash
./menu.sh --action cloud-set-key
./menu.sh --action cloud-enable --value 12
./menu.sh --action cloud-enable --value 12 --apply
./menu.sh --action cloud-status
```

| Attendu | Si ça échoue |
| --- | --- |
| [ ] Les contrôles sans `--apply` passent : secret bloqué, appel sain relayé, plafond respecté | Le cloud reste désactivé ; lire le contrôle en échec |
| [ ] `CLOUD_STATUS ready=1`, `CLOUD_MODEL name=standard`, budget à 0 € | Revoir la clé (`cloud-set-key`) et sa limite chez OpenRouter |

**Filtre de confidentialité, sans rien envoyer de réel :**

```bash
printf 'NomFictifReception42\n' >> /data/IA/Openclaw/state/cloud/denylist.txt
```

- [ ] Dans WebUI, avec un rôle « · cloud (DeepSeek) », écrire « Parle-moi de NomFictifReception42 ». La réponse **repasse en local** avec un bandeau 🔒, et rien n'apparaît dans l'activité OpenRouter.

**Un appel Flash (standard) :**

- [ ] Poser une question publique, par exemple « Compare Ansible et Terraform pour configurer 3 serveurs ». Le bandeau ☁️ indique « Modèle : DeepSeek V4.1 Flash 1017 ».
- [ ] `!budget` dans le chat affiche un petit montant, le profil et le modèle `standard`.

**Un appel de raisonnement profond (V4 Pro) :**

```bash
./menu.sh --action cloud-set-profile --value approfondi --apply
./menu.sh --action cloud-set-model --value profond
./menu.sh --action cloud-set-model --value profond --apply
```

- [ ] La simulation (sans `--apply`) affiche `max_usd_per_million=1.4/3.2` ; le choix est ensuite confirmé.
- [ ] Une question exigeante reçoit une réponse dont le bandeau indique « Modèle : DeepSeek V4 Pro 0423 ».
- [ ] Dans l'**activité OpenRouter**, le fournisseur utilisé est l'un de SiliconFlow, DigitalOcean, Cloudflare ou DeepInfra, et le prix est sous 1,40 $ / 3,20 $ par million. Sinon, noter le fournisseur et le prix affichés et me les transmettre.
- [ ] **Si l'appel échoue** avec « aucun fournisseur » ou une erreur 404/503 : revenir en `standard` (commande ci-dessous) et noter le message exact. Les fournisseurs ont peut-être changé depuis le [relevé du 2 novembre](audits/2026-11-02/openrouter-deepseek-v4-pro.md).

**Rapprochement et retour au standard :**

```bash
./menu.sh --action cloud-reconcile --value MONTANT_FACTURE_EN_EUROS --apply
./menu.sh --action cloud-set-model --value standard --apply
```

- [ ] Le montant facturé par OpenRouter correspond à peu près au journal (`cloud-status`).
- [ ] Facultatif : `./menu.sh --action cloud-disable --apply` ; tout redevient local.

## Phase 11 — Mesures facultatives

À faire seulement si tu veux mesurer plus finement, ou si une anomalie apparaît :

- `./menu.sh --action acceptance-32k --apply` : capacité 32K sur la B580 ;
- cinq cycles de veille et réveil, puis `quick-check` ;
- la [qualification détaillée Fedora et GPU](QUALIFICATION_FINALE_FEDORA.md) et la [grille pédagogique sur 20](EVALUATION_PEDAGOGIE.md).

## Journal de réception à remplir

| Phase | Date | Résultat (PASS / FAIL / non fait) | Notes (versions, VRAM, temps de réponse, coût) |
| --- | --- | --- | --- |
| 1. Fedora | | | |
| 2. `/data` | | | |
| 3. Pré-contrôle | | | |
| 4. Installation | | | |
| 5. WebUI | | | |
| 6. quick-check | | | |
| 7. Chat local | | | |
| 8. Projet | | | |
| 9. Sauvegarde et redémarrage | | | |
| 10. Cloud | | | |

**À me transmettre en cas d'échec ou à la fin :** la phase concernée, la commande exacte et les lignes `…_RESULT=`, `PRECHECK=`, `RECEPTION=` et `FAIL` affichées. **Jamais** la clé OpenRouter, le contenu de `state/cloud/` ni une conversation privée. Une fois la réception réussie, ces résultats permettront de mettre `STATUS.md` à jour avec des preuves datées.
