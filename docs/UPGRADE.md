# Upgrade contrôlé

## Repères de progression

| Repère | Valeur |
|---|---|
| **Pour qui** | Toute personne qui suit le parcours et veut apprendre à faire évoluer la plateforme sans perdre la capacité d’expliquer ou de rollback un changement. |
| **Position dans le parcours** | 12/14 |
| **Prérequis** | Avoir lu [`KERNEL_POLICY.md`](KERNEL_POLICY.md) et compris la règle « une variable à la fois ». |
| **Objectif** | Apprendre à préparer, appliquer, vérifier et annuler un changement de version, modèle, quantification, Mesa, kernel ou runtime. |
| **Résultat attendu** | Savoir construire une comparaison avant/après attribuable à une seule variable et identifier les gates à rejouer. |
| **Critère d’arrêt** | Ne pas appliquer un upgrade si la baseline, le backup, le rollback ou les preuves à invalider ne sont pas identifiés. |
| **Continuer avec** | [`QUALIFICATION.md`](QUALIFICATION.md) |
| **Source de vérité** | `config/runtime_versions.yaml`, `config/model_catalog.yaml`, `config/optimization_policy.yaml` et les preuves avant/après. |

Les upgrades de `OPENCLAW_LOCAL_FEDORA` suivent une règle simple : **une variable à la fois, avec baseline connue, preuves avant/après et rollback préparé**.

Une version plus récente n'est pas automatiquement meilleure ni qualifiée.

## Avant tout upgrade

Exécuter :

```bash
./menu.sh --action validate
./menu.sh --action health
./menu.sh --action backup
```

Noter l'état courant :

```bash
cat /etc/fedora-release
uname -r
openclaw --version
ollama --version
ollama list
vulkaninfo --summary
```

Conserver les preuves de qualification encore valides et identifier celles que le changement invalidera.

## Principe de changement unique

Ne pas modifier dans la même campagne :

- OpenClaw + Ollama ;
- modèle + quantification ;
- kernel + Mesa ;
- backend + kernel ;
- modèle + contexte ;
- plusieurs modèles nominaux simultanément.

Le but est de pouvoir attribuer un changement de comportement à une seule variable.

## Source de vérité

Les pins approuvés sont dans :

```text
config/runtime_versions.yaml
config/model_catalog.yaml
config/optimization_policy.yaml
```

La documentation décrit le processus ; elle ne remplace pas ces contrats.

## Upgrade OpenClaw

### Préparation

1. identifier la version candidate ;
2. vérifier ses notes de version et changements de schéma ;
3. créer une branche dédiée ;
4. mettre à jour le pin contractuel et ses métadonnées vérifiables ;
5. adapter les tests et le renderer si le schéma change.

### Validation logicielle

```bash
./menu.sh --action validate
make ci
```

### Validation machine

Après installation de la candidate :

```bash
openclaw --version
./menu.sh --action configure-openclaw --backend ollama-vulkan
./menu.sh --action health
./menu.sh --action e2e --backend ollama-vulkan
```

Selon l'impact, rejouer L5/L7 avant d'accepter la nouvelle baseline.

### Rollback

Rétablir le pin OpenClaw précédent, réinstaller cette version, réappliquer la configuration et rejouer `health` + L4.

## Upgrade du plugin Parallel

Traiter le plugin comme une variable distincte d'OpenClaw lorsque c'est possible.

Vérifier :

- package exact ;
- version exacte ;
- provider `parallel-free` ;
- schéma OpenClaw ;
- recherche Web ;
- absence d'impact sur le routage LLM local-only.

Rejouer les tests de configuration OpenClaw et les cas Web pertinents.

## Upgrade Ollama

### Préparation

Enregistrer :

```bash
ollama --version
ollama list
```

### Candidate

Mettre à jour le contrat dans une branche dédiée puis valider la CI.

### Machine cible

Après installation :

```bash
ollama --version
systemctl status ollama.service --no-pager
ollama list
./menu.sh --action health
```

Un changement Ollama peut modifier chargement modèles, performance, tool-calling ou comportement GPU. Rejouer les gates matériels/performance appropriés avant promotion.

### Rollback

Revenir à la version précédente et vérifier que les digests modèles et le comportement baseline sont inchangés.

## Upgrade d'un modèle nominal

C'est un changement d'architecture, même si l'alias logique reste identique.

Étapes minimales :

1. définir le nouveau runtime ID et la quantification ;
2. vérifier licence, source et capacité ;
3. mettre à jour `config/model_catalog.yaml` ;
4. conserver exactement trois alias routés ;
5. adapter qualification et tests spécifiques ;
6. CI ;
7. provisionnement explicite ;
8. identité/digest ;
9. E2E ;
10. HARD-40M ;
11. Golden Projects ;
12. revue humaine.

Un challenger ne devient jamais nominal uniquement parce qu'il est plus rapide.

## Changer la quantification

Changer `Q4_K_M` vers une autre quantification est une variable à part entière. Refaire les comparaisons de qualité, VRAM, RAM, TTFT, débit, stabilité et comportement outils. Ne pas réutiliser les preuves de l'ancienne quantification.

## Upgrade Mesa / pile Vulkan

Fedora peut mettre à jour Mesa indépendamment du projet.

Avant :

```bash
rpm -q mesa-vulkan-drivers
vulkaninfo --summary
```

Après :

```bash
rpm -q mesa-vulkan-drivers
vulkaninfo --summary
./menu.sh --action hardware-l3
./menu.sh --action health
```

Une évolution Mesa susceptible d'affecter la B580 doit conduire à de nouvelles mesures avant de comparer des performances.

## Kernel Fedora officiel

Les mises à jour du kernel Fedora nominal restent distinctes du candidat upstream L6.

Après une mise à jour Fedora :

```bash
uname -r
lsmod | grep '^xe '
vulkaninfo --summary
./menu.sh --action hardware-l3
```

Conserver au moins un kernel Fedora fonctionnel permettant le rollback.

## Kernel upstream candidat

Le candidat défini par la politique kernel ne devient jamais le default automatiquement.

Pour le promouvoir, il doit être comparé au kernel Fedora officiel avec les mêmes conditions de runtime, modèles, prompts et contextes, puis satisfaire les gates de `KERNEL_POLICY.md` et `QUALIFICATION.md`.

## Upgrade llama.cpp/Vulkan

`llama-cpp-vulkan` est l'unique candidat runtime L6.

Toute modification de version/tag/commit doit :

- mettre à jour le pin ;
- reconstruire/reprovisionner de façon reproductible ;
- conserver l'endpoint loopback ;
- refaire les comparaisons L6 sur plusieurs runs ;
- préserver la baseline Ollama/Vulkan disponible.

## Upgrade Fedora majeur

Passer de Fedora 44 à une autre version n'est pas un simple update de package. C'est une nouvelle cible plateforme.

Avant de déclarer la nouvelle version supportée, revalider au minimum :

- bootstrap ;
- SELinux ;
- firewalld ;
- `systemd --user` ;
- `xe` ;
- Mesa/Vulkan ;
- Podman ;
- KVM/libvirt ;
- Ollama ;
- OpenClaw ;
- L2/L3/L4/L5 ;
- Golden Projects ;
- documentation et CI de la nouvelle version.

Ne pas remplacer `fedora:44` dans CI sans traiter explicitement ce changement comme une migration de plateforme.

## Après chaque upgrade

Toujours terminer par :

```bash
./menu.sh --action validate
./menu.sh --action health
```

Puis rejouer les gates affectés.

Mettre à jour `STATUS.md` uniquement avec des états réellement observés.

## Matrice indicative de requalification

| Variable changée | Minimum à rejouer |
|---|---|
| documentation seule | CI documentaire / contrats |
| config OpenClaw | health + L4 |
| OpenClaw | health + L4, puis gates fonctionnels impactés |
| Parallel | config + recherche Web + tests associés |
| Ollama | health + L4 + L5/L6 selon impact |
| modèle nominal | L4 + L5 + L7 + revue humaine |
| quantification | L4 + L5 + L6 + L7 |
| Mesa/Vulkan | L3 + L4 + performance concernée |
| kernel Fedora | L3 + L4 + L5 selon impact |
| kernel candidat | protocole L6 complet |
| backend llama.cpp/Vulkan | protocole L6 complet |
| Fedora majeure | requalification plateforme complète |

## Critère d'acceptation

Un upgrade est accepté lorsque le dépôt, la machine cible et les preuves nécessaires sont cohérents avec les nouveaux contrats et que le rollback reste possible.

« Plus récent » n'est jamais un critère suffisant de promotion.
