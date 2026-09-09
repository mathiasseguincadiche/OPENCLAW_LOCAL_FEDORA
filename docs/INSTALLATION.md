# Installation Fedora 44

Ce guide couvre la mise en service de `OPENCLAW_LOCAL_FEDORA` sur la plateforme cible. Il décrit l'installation du produit ; il ne remplace pas la qualification matérielle L2–L8.

## Cible supportée

La cible nominale est :

- Fedora Linux 44 Workstation ;
- GNOME 50 / Wayland ;
- Intel Arc B580 12 Gio ;
- driver kernel `xe` ;
- Mesa/Vulkan ;
- SELinux **Enforcing** ;
- firewalld actif ;
- OpenClaw Gateway géré par `systemd --user` ;
- Ollama/Vulkan comme runtime baseline.

La racine runtime préférée est `/srv/openclaw-local`. Le code sait utiliser un fallback utilisateur lorsque cette racine n'est pas disponible, mais la machine cible doit privilégier le volume dédié prévu pour les données lourdes.

## Avant de commencer

### Firmware / matériel

Vérifier dans l'UEFI/BIOS :

- boot UEFI ;
- Resizable BAR activé pour la B580 ;
- le disque prévu pour la racine runtime est visible ;
- le kernel Fedora officiel reste la voie de démarrage et de rollback.

Aucun kernel upstream candidat ne doit être installé pendant le bootstrap initial.

### Session Fedora

Ouvrir une session graphique avec l'utilisateur qui exploitera OpenClaw. L'installation complète doit être lancée avec cet utilisateur, **pas directement en root**.

Contrôles rapides :

```bash
cat /etc/fedora-release
echo "$XDG_SESSION_TYPE"
getenforce
systemctl is-active firewalld
```

Résultats attendus : Fedora 44, `wayland`, `Enforcing`, et firewalld actif.

## Récupérer le dépôt

```bash
git clone https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA.git
cd OPENCLAW_LOCAL_FEDORA
```

Vérifier les contrats avant toute modification de la machine :

```bash
./menu.sh --action validate
```

Le dépôt doit échouer fermé si ses contrats ne sont pas cohérents.

## Étape 1 — Dry-run complet

Toujours commencer par :

```bash
./menu.sh --action install
```

Le dry-run affiche le plan sans effectuer l'installation. Le chemin nominal est :

1. bootstrap Fedora 44 ;
2. préparation du runtime géré ;
3. installation/convergence Ollama ;
4. installation/convergence OpenClaw ;
5. provisionnement explicite des trois modèles nominaux ;
6. déploiement des huit workspaces ;
7. configuration OpenClaw ;
8. installation du Gateway `systemd --user` ;
9. health-check final.

## Étape 2 — Bootstrap Fedora

Pour inspecter le bootstrap séparément :

```bash
./menu.sh --action bootstrap
```

Application :

```bash
./menu.sh --action bootstrap --apply
```

Le bootstrap doit préserver les invariants suivants :

- Fedora 44 ;
- SELinux Enforcing ;
- firewalld actif ;
- dépendances Mesa/Vulkan ;
- Podman ;
- KVM/libvirt/OVMF ;
- groupes GPU utiles (`render`, `video`) lorsqu'ils existent ;
- environnement Python géré ;
- racine runtime marquée par `.openclaw-fedora-runtime`.

Une reconnexion de session peut être nécessaire après modification des groupes utilisateur.

## Étape 3 — Installation complète

Lorsque le dry-run et le bootstrap sont compris :

```bash
./menu.sh --action install --apply
```

L'installateur converge vers les pins définis par les contrats du dépôt, notamment OpenClaw, le plugin Parallel et Ollama. Les valeurs canoniques sont dans `config/runtime_versions.yaml` ; le guide ne doit pas servir de second fichier de configuration.

L'installation complète active explicitement le Gateway OpenClaw en service utilisateur :

```bash
systemctl --user status openclaw-gateway.service
openclaw gateway status
```

## Étape 4 — Vérification du produit

Après installation :

```bash
./menu.sh --action health
```

Puis :

```bash
./menu.sh --action status
```

Le health-check couvre notamment :

- contrats du dépôt ;
- racine runtime ;
- CLI OpenClaw ;
- Gateway ;
- Ollama ;
- inventaire des trois modèles nominaux ;
- huit workspaces agents gérés.

Pour la vérification opérateur détaillée, voir [`OPERATIONS.md`](OPERATIONS.md).

## Étape 5 — Vérification GPU sans revendiquer une qualification

Contrôles de base :

```bash
lspci -Dnn | grep -Ei 'vga|display'
lsmod | grep '^xe '
ls -l /dev/dri
rpm -q mesa-vulkan-drivers
vulkaninfo --summary
```

Ces commandes permettent de diagnostiquer la pile. Elles ne remplacent pas les gates de qualification.

Les preuves formelles sont produites par :

```bash
./menu.sh --action hardware-l2
./menu.sh --action hardware-l3
```

Voir [`QUALIFICATION.md`](QUALIFICATION.md) avant d'exécuter une campagne de qualification.

## Installation séparée des modèles

Le provisionnement nominal peut être planifié séparément :

```bash
./menu.sh --action models
```

Puis appliqué explicitement :

```bash
./menu.sh --action models --apply
```

Le provisionnement nominal contient exactement les trois modèles routés définis dans `config/model_catalog.yaml`. Le challenger Granite n'est pas un quatrième modèle nominal et utilise le chemin L6 dédié.

## Configuration OpenClaw séparée

Dry-run baseline :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan
```

Application :

```bash
./menu.sh --action configure-openclaw --backend ollama-vulkan --apply
```

Les backends `llama-cpp-vulkan` et `llama-cpp-sycl` sont des candidats L6. Ils ne doivent pas être choisis comme nouveaux defaults sans qualification et décision humaine.

## Stockage

La racine gérée contient typiquement :

```text
/srv/openclaw-local/
├── .openclaw-fedora-runtime
├── runtime/
├── models/
├── workspaces/
├── projects/
├── proofs/
├── benchmarks/
├── state/
└── backups/
```

Les poids modèles, preuves runtime et données lourdes ne sont pas versionnés dans Git.

## Après installation

Ordre recommandé :

```bash
./menu.sh --action health
./menu.sh --action project-selftest
./menu.sh --action e2e-dry-run --backend ollama-vulkan
./menu.sh --action qualification-dry-run
```

Le `project-selftest` est un test logiciel synthétique. Le `e2e-dry-run` et le `qualification-dry-run` valident des plans. Aucun de ces résultats n'est un PASS matériel B580.

## Échec d'installation

Ne contourner ni SELinux, ni firewalld, ni les contrôles de version pour obtenir artificiellement un PASS.

Utiliser d'abord :

```bash
./menu.sh --action health
systemctl --user status openclaw-gateway.service
journalctl --user -u openclaw-gateway.service -n 200 --no-pager
systemctl status ollama.service
```

Puis suivre [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

## Réparation ou retour arrière

Le chemin de réparation officiel commence par une sauvegarde :

```bash
./menu.sh --action repair
./menu.sh --action repair --apply
```

Pour les procédures d'exploitation, de sauvegarde et de restauration, voir [`OPERATIONS.md`](OPERATIONS.md) et [`LIFECYCLE.md`](LIFECYCLE.md).

## Installation réussie ≠ qualification matérielle

Une installation est considérée fonctionnellement en place lorsque le health-check et les contrôles logiciels passent. Elle n'est **pas** pour autant qualifiée B580, Vulkan, HARD-40M, L6 ou V1.

La qualification réelle suit les gates L2 à L8 sur la machine cible.
