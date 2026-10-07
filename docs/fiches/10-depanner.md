# Dépanner

[← Guide](../GUIDE.md)

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

Message « digest déjà adopté divergent » : le modèle a été retéléchargé dans une version différente de celle enregistrée à l'installation. Si c'est voulu, supprime `/srv/openclaw-local/state/model-identities.json` puis relance `./menu.sh --action install --apply`.

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

Corrige le chemin ou le contexte du fichier concerné. Pour le dossier de l'atelier : `sudo restorecon -RF /srv/openclaw-local`.

## Permission refusée sous `/srv/openclaw-local`

```bash
namei -l /srv/openclaw-local
ls -ldZ /srv/openclaw-local
```

Le dossier doit t'appartenir. Ne règle pas le problème avec `chmod -R 777`.

## Plus de place

```bash
du -sh /srv/openclaw-local/* | sort -h
```

Supprime d'anciennes sauvegardes dans `backups/`.

## Demander de l'aide

Rassemble ces informations, sans mot de passe ni contenu privé :

```bash
cat /etc/fedora-release; uname -r; getenforce
openclaw --version; ollama --version; ollama list
./menu.sh --action health
vulkaninfo --summary
```

Ajoute les lignes de journal qui entourent l'erreur.
