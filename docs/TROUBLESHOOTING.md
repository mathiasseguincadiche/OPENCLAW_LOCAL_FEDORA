# Dépannage par symptôme

## Repères de lecture

| Repère | Valeur |
|---|---|
| **Public cible** | Opérateurs confrontés à un incident, une anomalie ou un gate en échec. |
| **Niveau** | Intermédiaire |
| **Prérequis** | Disposer d'un symptôme observable et pouvoir exécuter `validate`, `health` et les commandes de diagnostic de la couche concernée. |
| **Objectif** | Isoler la couche fautive et appliquer la correction minimale sans masquer l'échec ni affaiblir la sécurité. |
| **Résultat attendu** | Savoir collecter les preuves utiles, vérifier la correction et décider d'un rollback ou d'une escalade. |
| **Critère d’arrêt** | Arrêter toute correction qui exigerait `setenforce 0`, `chmod -R 777`, une exposition réseau inutile, un changement de modèle/backend non justifié ou plusieurs variables à la fois. |
| **À lire ensuite** | [`OPERATIONS.md`](OPERATIONS.md) après retour à l'état sain, ou [`UPGRADE.md`](UPGRADE.md) si la correction implique un changement volontaire de version. |
| **Source de vérité** | Les contrats `config/*.yaml`, les logs systemd/OpenClaw/Ollama et les preuves runtime du gate en échec. |

Ce guide part du symptôme observé et suit toujours la même méthode : **observer → isoler → corriger au minimum → vérifier → rollback si nécessaire**.

Ne pas désactiver SELinux, ouvrir le firewall, changer de modèle ou basculer de backend uniquement pour masquer un échec.

## Diagnostic de base

Commencer par :

```bash
./menu.sh --action validate
./menu.sh --action health
```

Puis collecter l'état utile :

```bash
cat /etc/fedora-release
uname -r
getenforce
openclaw --version
ollama --version
openclaw gateway status
ollama list
```

## Gateway OpenClaw ne démarre pas

### Diagnostic

```bash
systemctl --user status openclaw-gateway.service --no-pager
journalctl --user -u openclaw-gateway.service -n 200 --no-pager
openclaw gateway status
```

Vérifier ensuite la configuration par dry-run :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan
```

### Corrections possibles

- corriger une configuration invalide via le configurateur du dépôt ;
- vérifier que l'utilisateur possède une session `systemd --user` fonctionnelle ;
- réappliquer la configuration nominale avec `--apply` uniquement après un dry-run compris ;
- utiliser `repair --apply` si l'état géré est devenu incohérent.

### Vérification

```bash
systemctl --user restart openclaw-gateway.service
openclaw gateway status
./menu.sh --action health
```

## Gateway actif mais agents injoignables

### Diagnostic

```bash
./menu.sh --action health
openclaw gateway status
```

Vérifier que les huit workspaces gérés existent et que la configuration attendue est rendue.

### Correction

```bash
./menu.sh --action agents
./menu.sh --action configure-openclaw --backend ollama-vulkan
```

Si le dry-run est correct :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan --apply
systemctl --user restart openclaw-gateway.service
```

## Ollama ne répond pas

### Diagnostic

```bash
systemctl status ollama.service --no-pager
journalctl -u ollama.service -n 200 --no-pager
ollama --version
ollama list
```

### Correction

Si le service existe mais est arrêté :

```bash
sudo systemctl restart ollama.service
```

Puis :

```bash
ollama list
./menu.sh --action health
```

Ne pas remplacer Ollama par un backend candidat pour contourner une panne de la baseline.

## Un modèle nominal manque

### Diagnostic

```bash
ollama list
```

Comparer à `config/model_catalog.yaml`.

### Correction

```bash
./menu.sh --action models
./menu.sh --action models --apply
```

Le téléchargement pendant un benchmark reste interdit.

## Mauvais modèle ou mauvais provider observé

### Diagnostic

1. vérifier `config/model_catalog.yaml` ;
2. vérifier `config/core/model_routing.yaml` ;
3. exécuter le dry-run OpenClaw :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan
```

Ne pas modifier directement les workspaces pour contourner les contrats de routage.

### Correction

Réappliquer le rendu contractuel :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan --apply
```

Puis redémarrer le Gateway et lancer `health`.

## B580 non détectée

### Diagnostic PCI

```bash
lspci -Dnn | grep -Ei 'vga|display'
```

Si la carte n'apparaît pas, le problème est en dessous du runtime IA : firmware, alimentation, slot PCIe ou matériel.

### Diagnostic driver

```bash
lsmod | grep '^xe '
```

Puis :

```bash
journalctl -k -b | grep -Ei 'xe|drm|intel'
```

Ne pas installer un kernel candidat avant d'avoir compris l'état du kernel Fedora nominal.

## `/dev/dri/renderD*` absent

```bash
ls -l /dev/dri
id
```

Vérifier que `xe` est chargé et que l'utilisateur dispose des groupes nécessaires. Une reconnexion de session peut être requise après ajout à `render` ou `video`.

Rejouer ensuite le gate L3 :

```bash
./menu.sh --action hardware-l3
```

## Vulkan ne voit pas la B580

```bash
rpm -q mesa-vulkan-drivers
vulkaninfo --summary
```

Vérifier que la pile Mesa/Vulkan Fedora est installée avant toute tentative de backend alternatif.

Ne pas conclure que la carte est qualifiée uniquement parce que `vulkaninfo` la voit ; L3 reste le gate formel.

## SELinux bloque une opération

### Diagnostic

```bash
getenforce
sudo ausearch -m AVC,USER_AVC -ts recent
```

Le résultat nominal de `getenforce` reste `Enforcing`.

### Correction

Corriger le chemin, le contexte, les permissions ou la politique applicable. Le bootstrap utilise les primitives Fedora prévues pour restaurer les contextes gérés.

### Interdit comme « solution »

```text
setenforce 0
```

Une désactivation temporaire peut modifier le symptôme mais ne constitue pas une correction acceptable ni une preuve de conformité.

## Firewalld semble bloquer OpenClaw

Le Gateway et les providers nominaux sont loopback-only. Avant de créer une règle firewall :

```bash
systemctl is-active firewalld
sudo firewall-cmd --state
openclaw gateway status
```

Un problème loopback est généralement un problème de service, d'endpoint ou de configuration, pas une raison d'exposer le service sur le réseau.

## `systemd --user` ne fonctionne pas

```bash
systemctl --user status
loginctl show-user "$USER"
```

Vérifier que l'installation est exécutée depuis le compte utilisateur de bureau attendu. Le lingering est un choix explicite du lifecycle, pas un contournement général des problèmes de session.

## Permission refusée sous `/srv/openclaw-local`

```bash
namei -l /srv/openclaw-local
ls -ldZ /srv/openclaw-local
id
```

Vérifier propriétaire, groupe et contexte SELinux. Ne pas résoudre avec un `chmod -R 777`.

Après correction :

```bash
./menu.sh --action health
```

## Espace disque insuffisant

```bash
df -h /srv/openclaw-local
df -i /srv/openclaw-local
du -sh /srv/openclaw-local/* 2>/dev/null | sort -h
```

Prioriser une stratégie explicite de rétention pour backups et résultats temporaires. Ne pas supprimer des preuves référencées par un rapport L8 existant.

## OpenClaw n'a pas la version contractuelle

```bash
openclaw --version
```

Comparer à `config/runtime_versions.yaml`.

Ne pas modifier le contrat pour accepter silencieusement la version installée. Suivre [`UPGRADE.md`](UPGRADE.md) si le changement de version est volontaire ; sinon revenir au pin contractuel.

## Ollama n'a pas la version contractuelle

```bash
ollama --version
```

Même principe : soit restaurer le pin attendu, soit traiter le changement comme un upgrade contrôlé avec requalification adaptée.

## Le plugin Parallel est incohérent

Le pin et le provider attendus sont définis dans `config/runtime_versions.yaml` et les contrats OpenClaw.

Réexécuter d'abord :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan
```

Puis appliquer uniquement si le plan est correct.

## `project-selftest` échoue

```bash
./menu.sh --action validate
./menu.sh --action project-selftest
```

Un échec ici est logiciel et ne nécessite pas la B580. Conserver l'erreur exacte, les chemins et le statut des contrats avant de toucher aux runtimes IA.

## L4 E2E échoue

Conserver la preuve produite. Vérifier dans cet ordre :

1. `health` ;
2. Gateway ;
3. Ollama ;
4. modèles exacts ;
5. configuration OpenClaw ;
6. workspaces agents ;
7. provider réellement observé ;
8. tool-calling / repair concerné.

Ne pas basculer vers un backend candidat ou cloud pour faire passer L4.

## HARD-40M L5 échoue

Ne pas relancer en abaissant les seuils.

Identifier la catégorie :

- erreur API ;
- timeout ;
- check fonctionnel ;
- TTFT ;
- débit ;
- identité modèle ;
- contexte ;
- préflight L2/L3.

Comparer la preuve à `config/qualification_policy.yaml` et lire [`QUALIFICATION.md`](QUALIFICATION.md).

## L6 montre un candidat plus rapide

Un gain de performance n'est pas une promotion.

Vérifier :

- nombre de runs ;
- même kernel lorsque requis ;
- même backend lorsque requis ;
- mêmes prompts/contextes ;
- absence de régression fonctionnelle ;
- absence de régression sécurité ;
- seuils de performance ;
- décision humaine.

## L8 reste `BLOCKED`

C'est normal tant qu'une preuve requise L2–L7 est absente, invalide ou incohérente.

```bash
./menu.sh --action release-readiness
```

Traiter chaque gate bloquant. Ne pas créer manuellement un fichier PASS.

## Backup invalide ou restauration refusée

La restauration est volontairement fail-closed sur les archives dangereuses, chemins traversants, liens et destination incorrecte.

Inspecter le message d'erreur puis créer une nouvelle sauvegarde si la source runtime est saine :

```bash
./menu.sh --action backup
```

Ne pas désactiver les contrôles d'archive pour récupérer une sauvegarde suspecte.

## Réparation n'a pas résolu le problème

Après :

```bash
./menu.sh --action repair --apply
```

si `health` échoue encore, ne répéter pas la réparation en boucle. Revenir au symptôme précis, collecter les journaux et identifier la couche fautive : Fedora, GPU, Ollama, OpenClaw, modèle, workspace ou moteur projet.

## Incident : informations à fournir

Fournir au minimum :

- Fedora release ;
- kernel ;
- état SELinux ;
- version OpenClaw ;
- version Ollama ;
- statut Gateway ;
- statut Ollama ;
- inventaire modèles ;
- résumé Vulkan si pertinent ;
- commande exacte en échec ;
- sortie d'erreur pertinente ;
- étape L0–L8 concernée.

Ne jamais joindre de secrets, tokens, prompts privés, réponses de modèles contenant des données sensibles ou documents projet confidentiels.

## Si aucun cas ne correspond

Suivre le runbook général [`OPERATIONS.md`](OPERATIONS.md), collecter un état minimal et traiter le système couche par couche. Une panne non comprise ne justifie pas de modifier plusieurs variables simultanément.
