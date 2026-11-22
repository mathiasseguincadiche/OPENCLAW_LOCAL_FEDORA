# Dépanner

[← Guide](../GUIDE.md) · [Carte des composants](11-comment-ca-marche.md)

Commence par identifier la **couche** en panne : interface, pont, OpenClaw, Ollama, matériel ou passerelle cloud. Le diagramme te montre les dépendances pour éviter de corriger le mauvais service.

## La méthode

Observer, isoler la couche en cause, corriger le minimum, vérifier. Commence toujours par :

```bash
./menu.sh --action health
```

Les couches, de bas en haut : matériel et pilote → Vulkan → Ollama → modèle → OpenClaw → chat et atelier. Une couche ne peut pas fonctionner si celle du dessous est en panne : remonte dans cet ordre.

Deux choses à ne jamais faire pour « que ça passe » : désactiver SELinux (`setenforce 0`) ou ouvrir le pare-feu. Tout écoute sur `127.0.0.1` ; un blocage vient d'un service ou d'une configuration, pas du réseau.

## La carte graphique n'est pas vue

```bash
lspci -Dnn | grep -Ei 'vga|display'      # la carte est-elle présente ?
lsmod | grep '^xe '                      # le pilote est-il chargé ?
ls -l /dev/dri                           # y a-t-il un renderD* ?
vulkaninfo --summary                     # Vulkan la voit-il ?
./menu.sh --action check-gpu
```

| Constat | Piste |
|---|---|
| Absente de `lspci` | Matériel ou BIOS : alimentation, port PCIe, Resizable BAR |
| `xe` non chargé | `journalctl -k -b \| grep -Ei 'xe\|drm'` |
| Pas de `renderD*` accessible | Tu n'as pas rouvert ta session depuis l'installation (groupes `render` et `video`) |
| Vulkan ne la voit pas | `rpm -q mesa-vulkan-drivers` |

### Ollama voit la B580, mais ne peut pas ouvrir les périphériques GPU

Le service Ollama tourne avec un **compte système différent** de ta session GNOME. Le script `configure-ollama` lui attribue les groupes `render` et `video` **uniquement dans son unité systemd**, sans modifier durablement le compte. En cas d'accès refusé à `/dev/dri/renderD*`, examiner :

```bash
systemctl show ollama.service -p SupplementaryGroups
ls -l /dev/dri/renderD*
journalctl -u ollama.service -b --no-pager | grep -Ei 'permission|vulkan|render|device'
```

Si l'unité ne contient pas les groupes attendus, après le montage de `/data` et la vérification des journaux, relancer l'installation gérée (`./menu.sh --action install --apply`) depuis le répertoire GitHub, ou [réparer](09-entretenir.md), plutôt que d'ouvrir les permissions GPU à tous les comptes (`chmod 666`). Une CI verte ne garantit pas encore ce comportement sur la B580 réelle.

## Ollama ne répond pas

```bash
systemctl status ollama.service --no-pager
journalctl -u ollama.service -n 200 --no-pager
sudo systemctl restart ollama.service
```

Si le mode jeu est actif, Ollama est arrêté volontairement : `./menu.sh --action daily --apply`.

## Les réponses sont très lentes

Le modèle tourne probablement sur le processeur.

```bash
./menu.sh --action context-probe --apply
journalctl -u ollama -b | grep -i -E "vulkan|B580|vram"
```

- `CPU_ONLY` : Ollama n'utilise pas la carte. Vérifie la section précédente, puis `./menu.sh --action install --apply` pour réappliquer la configuration du service.
- `PARTIAL_CPU_OFFLOAD` : le contexte est trop grand pour la mémoire vidéo disponible. Ferme les applications qui utilisent la carte, ou réduis le contexte : [Réglages](08-reglages.md#changer-la-taille-du-contexte).

## Le modèle manque ou a changé

```bash
ollama list
./menu.sh --action models --apply
```

Message « digest déjà adopté divergent » : le modèle a été retéléchargé dans une version différente de celle enregistrée à l'installation. Si c'est voulu, supprime `/data/IA/Openclaw/state/model-identities.json` puis relance `./menu.sh --action install --apply`.

## OpenClaw ne démarre pas

```bash
systemctl --user status openclaw-gateway.service --no-pager
journalctl --user -u openclaw-gateway.service -n 200 --no-pager
./menu.sh --action configure-openclaw          # aperçu de la configuration
./menu.sh --action repair --apply
```

## « OpenClaw divergent » ou « Ollama divergent »

La version installée n'est pas celle écrite dans `config/runtime_versions.yaml`. Une mise à jour s'est faite en dehors du projet.

```bash
openclaw --version
ollama --version
./menu.sh --action upgrade --apply    # revient aux versions prévues
```

## Le chat répond « occupé » ou une erreur

- Une génération est déjà en cours, dans le chat ou l'atelier : attends sa fin.
- Le mode jeu est actif : `./menu.sh --action daily --apply`.
- Sinon : `./menu.sh --action webui-status`, puis `journalctl --user -u clawfedora-webui-bridge.service -n 100 --no-pager`.

## Le chat ne s'ouvre pas

```bash
./menu.sh --action webui-status
podman ps -a --filter name=clawfedora-webui
journalctl --user -u clawfedora-webui.service -n 100 --no-pager
```

## SELinux bloque quelque chose

```bash
getenforce                                   # doit rester Enforcing
sudo ausearch -m AVC,USER_AVC -ts recent     # ce qui a été refusé
```

Corrige le chemin ou le contexte du fichier concerné. Pour le dossier de l'atelier : `sudo restorecon -RF /data/IA/Openclaw`.

## Permission refusée sous `/data/IA/Openclaw`

```bash
namei -l /data/IA/Openclaw
ls -ldZ /data/IA/Openclaw
```

Le dossier doit t'appartenir. Ne règle pas le problème avec `chmod -R 777`.

## Plus de place

```bash
du -sh /data/IA/Openclaw/* | sort -h
```

Supprime d'anciennes sauvegardes dans `backups/`.

## L'ancienne route OpenRouter apparaît encore

Depuis le passage à Qwen + Ornith, aucun modèle cloud n'est autorisé. Un ancien service ou une clé peut néanmoins rester sur une installation existante tant que tu n'as pas exécuté son retrait contrôlé.

```bash
./menu.sh --action local-retire-cloud
./menu.sh --action local-retire-cloud --apply
./menu.sh --action configure-openclaw --apply
./menu.sh --action health
```

Si un ancien projet présente une approbation cloud, ses données ne doivent pas être perdues : la politique locale ignore cette autorisation et impose l'inférence Ollama. Vérifier l'état du projet et le journal avant toute suppression manuelle.

## Demander de l'aide

Rassemble ces informations, sans mot de passe ni contenu privé :

```bash
cat /etc/fedora-release; uname -r; getenforce
openclaw --version; ollama --version; ollama list
./menu.sh --action health
vulkaninfo --summary
```

Ajoute les lignes de journal qui entourent l'erreur.
