# Qualification Fedora

## Repères de progression

| Repère | Valeur |
|---|---|
| **Pour qui** | Toute personne qui a suivi le parcours et veut comprendre comment le projet transforme des observations en preuves reproductibles. |
| **Position dans le parcours** | 13/14 |
| **Prérequis** | Avoir lu [`UPGRADE.md`](UPGRADE.md) et compris baseline, changement unique, rollback et preuves runtime. |
| **Objectif** | Comprendre puis exécuter correctement les gates L2 à L8, HARD-40M, L6 et l’approbation humaine. |
| **Résultat attendu** | Savoir ce que chaque gate prouve, où les preuves sont stockées et pourquoi aucune CI ne remplace la machine réelle. |
| **Critère d’arrêt** | Ne jamais poursuivre vers un gate supérieur si le gate précédent est absent, en échec ou mal compris. |
| **Continuer avec** | [`ROADMAP.md`](ROADMAP.md) |
| **Source de vérité** | `config/qualification_policy.yaml`, `config/optimization_policy.yaml`, `config/release_readiness.yaml` et les preuves runtime. |

## Principe

La qualification est entièrement Linux-native et avance par preuves :

```text
L2 Fedora/hardware
        ↓
L3 B580 xe + Mesa/Vulkan
        ↓
L4 OpenClaw + 8 agents + outils
        ↓
L5 HARD-40M Ollama Vulkan
        ↓
L6 runtime Vulkan + kernel + Ministral ↔ Granite (slot DevOps)
        ↓
L7 Golden Projects + projet représentatif
        ↓
L8 Release Readiness
        ↓
Approbation humaine explicite
```

Aucun gate matériel n'est déclaré PASS par la CI. La CI valide le protocole, les contrats, les tests, les dry-runs et le comportement fail-closed. Les verdicts L2 à L6 nécessitent des preuves produites sur la machine Fedora 44 cible. L7 est vérifiable logiciellement en CI mais doit être rejoué sur l'installation finale avant L8.

## Flotte Architecture V2 qualifiée

La flotte routée doit rester exactement composée de trois alias :

- `qwen-max` → `qwen3.5:9b-q4_K_M` ;
- `gemma-deep` → `gemma4:12b-it-q4_K_M` ;
- `devstral-devops` → `hf.co/mistralai/Ministral-3-14B-Reasoning-2512-GGUF:Q4_K_M`.

`granite4.2:8b-q4_K_M` est uniquement un challenger L6 du slot `devstral-devops`. Il reste hors routage, hors flotte requise et ne peut jamais être promu automatiquement.

Le contexte nominal est 8192 tokens. Le contexte 16384 est un contexte de qualification, pas un réglage de production automatiquement promu.

## L2 — Fedora 44 / poste matériel

Commande :

```bash
./menu.sh --action hardware-l2
```

Le gate vérifie notamment :

- Fedora Linux 44 ;
- GNOME 50 ;
- session Wayland ;
- Ryzen 7 7700 et au moins 16 threads logiques ;
- au moins ~48 Gio installés, avec tolérance pour la mémoire réservée au firmware ;
- boot UEFI ;
- Intel Arc B580 ;
- Resizable BAR observé ;
- SELinux Enforcing ;
- `systemd --user` opérationnel.

La preuve JSON est écrite hors Git sous `proofs/hardware/`.

## L3 — Intel Arc B580 Vulkan

Commande :

```bash
./menu.sh --action hardware-l3
```

Le gate exige :

- Arc B580 détectée ;
- module kernel `xe` chargé ;
- render node `/dev/dri/renderD*` ;
- utilisateur membre du groupe `render` ;
- paquet `mesa-vulkan-drivers` ;
- `vulkaninfo --summary` confirmant la B580 Intel.

La pile GPU supportée par le projet est `xe` + Mesa/Vulkan.

## L4 — OpenClaw E2E

La version de qualification OpenClaw est verrouillée par `config/runtime_versions.yaml` et vaut actuellement `2026.9.2`.

Dry-run :

```bash
./menu.sh --action e2e-dry-run --backend ollama-vulkan
```

Run réel :

```bash
./menu.sh --action e2e --backend ollama-vulkan
```

L4 vérifie :

- version OpenClaw verrouillée ;
- configuration valide ;
- Gateway RPC réellement disponible ;
- exactement 8 agents ;
- smoke déterministe des 8 agents ;
- preuve du provider local attendu ;
- transport Gateway sans fallback embedded ;
- écriture de fichier par outil ;
- erreur outil contrôlée puis réparation ;
- 3 runs de stabilité.

Le run réel est protégé contre la suspension par `systemd-inhibit`. L'entrée CLI réelle est fail-closed : elle refuse de lancer L4 si elle n'est pas appelée depuis le launcher Linux protégé.

## L5 — HARD-40M

Contrat :

- 3 modèles obligatoires ;
- exactement 30 cas ;
- 24 cas à 8K ;
- 6 cas à 16K ;
- 12 scénarios couverts collectivement à 8K ;
- 10 cas par modèle ;
- 3 probes Qwen avec reasoning natif, réservés à `qwen-max` ;
- plafond absolu de 768 tokens par scénario, avec 768 tokens sur les probes Qwen dédiés ;
- 210 s max par cas ;
- **2400 s / 40 min max pour le gate complet**, préflight et évaluation inclus ;
- endpoint Ollama loopback uniquement ;
- aucun appel cloud ;
- aucun téléchargement implicite de modèle ;
- identité exacte digest + quantification des trois modèles ;
- kernel, Mesa et version Ollama enregistrés ;
- aucune promotion automatique.

Le spécialiste `devstral-devops` conserve sa famille Ministral Reasoning propre. Il ne reçoit pas artificiellement les probes natifs Qwen.

### Dry-run

```bash
./menu.sh --action qualification-dry-run
```

Le dry-run valide la matrice et les contrats sans contacter Ollama ni le matériel.

### Profil performance

Vérification sans modification :

```bash
./menu.sh --action performance
```

Activation explicite :

```bash
./menu.sh --action performance --apply
```

Après la campagne, l'opérateur peut revenir explicitement à son profil habituel, par exemple :

```bash
./scripts/linux/08_power_profile.sh --profile balanced --apply
```

### Run réel

```bash
./menu.sh --action qualification
```

Le launcher utilise `systemd-inhibit --what=sleep --mode=block`. Le runner démarre son chronomètre avant L2/L3 et réduit automatiquement le budget benchmark du temps déjà consommé. Il ne peut donc pas dépasser volontairement la limite de 2400 secondes.

L'entrée CLI réelle revalide les contrats HARD-40M avant tout accès au matériel ou à Ollama. Un fichier suite hors contrat ne peut pas contourner les limites en lançant directement la CLI.

## Seuils L5

- taux d'erreur maximum : `0.0` ;
- taux de checks minimum : `0.875` ;
- médiane minimale : `6.0 tok/s` ;
- p95 premier token maximum : `12000 ms` ;
- 8K : au moins `0.875` de checks PASS ;
- 16K : au moins `0.75` de checks PASS.

Une sortie tronquée, une erreur API, une métrique de performance absente ou un timeout de cas déclenche un fail-fast, car le taux d'erreur autorisé est nul.

## Preuves

Les preuves ne sont pas versionnées dans Git. Elles sont stockées sous la racine runtime :

```text
/srv/openclaw-local/proofs/
├── hardware/
├── openclaw-e2e/
├── qualification/
├── l6/
├── l7/
└── l8/
```

Les preuves L2/L3 restent sous `proofs/hardware/`, y compris lorsqu'elles sont produites comme préflight d'un run HARD-40M. La preuve HARD-40M référence leurs chemins canoniques.

Les preuves HARD-40M et L6 ne stockent pas la sortie brute des modèles : elles conservent les SHA-256, longueurs/checks nécessaires, métriques, identités modèles et versions runtime.

## L6 — Comparaisons Linux

Après une baseline L5 PASS sur matériel réel, L6 compare une seule variable à la fois :

1. kernel Fedora officiel + Ollama/Vulkan — baseline ;
2. kernel Fedora officiel + llama.cpp/Vulkan — unique candidat runtime ;
3. kernel 7.2.3 + runtime retenu pour la comparaison ;
4. Ministral 3 14B Reasoning vs Granite 4.2 8B sur le même slot `devstral-devops` ;
5. trois runs minimum par série avant toute décision.

Le kernel Fedora officiel reste un rollback bootable obligatoire.

### Challenger Granite — hors routage

Le provisionnement nominal `models` reste limité aux trois modèles routés. Granite utilise un chemin distinct :

```bash
./menu.sh --action challenger-model
```

Le dry-run affiche le plan sans télécharger. Provisionnement explicite :

```bash
./menu.sh --action challenger-model --apply
```

La commande résout le runtime depuis `model_catalog.yaml` et appelle `ollama pull` uniquement pour `granite4.2:8b-q4_K_M`. Elle ne modifie jamais le routeur.

### Snapshots spécialiste/challenger

Collecte de l'incumbent Ministral :

```bash
clawfedora-l6 --runtime-root /srv/openclaw-local snapshot-challenger \
  --variant incumbent \
  --output /srv/openclaw-local/proofs/l6/challenger/ministral-run-1.json
```

Collecte du challenger Granite :

```bash
clawfedora-l6 --runtime-root /srv/openclaw-local snapshot-challenger \
  --variant challenger \
  --output /srv/openclaw-local/proofs/l6/challenger/granite-run-1.json
```

Répéter trois fois chaque variante. Le runner utilise le même corpus Fedora/DevOps de trois probes :

- plan systemd utilisateur exact, sans sudo ;
- tool-calling natif `inspect_service` avec arguments exacts ;
- réparation d'une mauvaise intention `system` vers `restart_user_unit` après retour d'outil.

Il enregistre `coding_pass`, `tool_calling_pass`, `tool_repair_pass`, `security_pass`, performances, identité/digest et hashes des sorties, sans persister les sorties brutes.

### Comparaison

```bash
clawfedora-l6 compare-challenger \
  --baseline /srv/openclaw-local/proofs/l6/challenger/ministral-run-1.json \
  --baseline /srv/openclaw-local/proofs/l6/challenger/ministral-run-2.json \
  --baseline /srv/openclaw-local/proofs/l6/challenger/ministral-run-3.json \
  --candidate /srv/openclaw-local/proofs/l6/challenger/granite-run-1.json \
  --candidate /srv/openclaw-local/proofs/l6/challenger/granite-run-2.json \
  --candidate /srv/openclaw-local/proofs/l6/challenger/granite-run-3.json \
  --output /srv/openclaw-local/proofs/l6/decisions/granite.json
```

Un résultat `ELIGIBLE_FOR_HUMAN_PROMOTION` n'effectue aucune promotion. Il signifie uniquement que Granite peut être présenté à une revue humaine comme candidat de remplacement du spécialiste DevOps. Tant qu'aucune décision humaine distincte n'est prise, Ministral reste le modèle nominal routé.

## L7 — Golden Projects

Validation du plan :

```bash
./menu.sh --action golden-dry-run
```

Run complet :

```bash
./menu.sh --action golden
```

L7 exécute cinq Golden Projects et un projet représentatif avec le vrai moteur projet et l'Artifact Exchange. Les projets doivent finir en `PACKAGING`, avec validation/review PASS, intégrité package et gate humain préservé. L7 n'appelle jamais `COMPLETE`.

## L8 — Release Readiness

Validation du framework sans preuves réelles :

```bash
./menu.sh --action release-readiness-dry-run
```

Agrégation réelle :

```bash
./menu.sh --action release-readiness
```

L8 :

- revalide les contrats logiciels ;
- exige les preuves réelles L2-L7 ;
- lie L2/L3 aux preuves référencées par L5 ;
- refuse un HARD-40M dont les seuils, timeouts ou matrice diffèrent du contrat courant ;
- exige les trois décisions L6 obligatoires : llama.cpp/Vulkan, kernel 7.2.3 et Ministral ↔ Granite ;
- recharge les snapshots et **recalcule** les décisions L6 avec les contrats courants ;
- exige L7 PASS avec six projets en `PACKAGING` et gate humain préservé ;
- produit un manifeste SHA-256 de toutes les preuves retenues.

Le résultat est uniquement `BLOCKED` ou `READY_FOR_HUMAN_REVIEW`. Même READY, V1 reste non approuvée.

## Approbation humaine L8

L'approbation n'est volontairement pas une action automatique du menu. Elle nécessite une commande explicite :

```bash
clawfedora-l8 --runtime-root /srv/openclaw-local approve \
  --report /srv/openclaw-local/proofs/l8/runs/<RUN>/RELEASE_READINESS_REPORT.json \
  --approver "Mathias" \
  --acknowledge-v1
```

Avant d'écrire l'enregistrement d'approbation, L8 recalcule la readiness et vérifie que le hash de l'ensemble de preuves est identique à celui du rapport soumis.

Le record `APPROVED_FOR_V1_PREPARATION` :

- est immuable ;
- atteste une approbation humaine explicite ;
- n'altère aucun fichier de configuration runtime ;
- ne promeut ni runtime, ni kernel, ni modèle ;
- ne passe aucun projet à `COMPLETE` ;
- ne crée aucun tag/release GitHub.

## Promotion

Aucune promotion automatique de backend, kernel, modèle challenger ou V1. Une preuve PASS rend seulement la configuration éligible à la revue humaine et aux gates suivants. L'approbation L8 autorise uniquement la préparation de V1 ; la publication effective reste une opération séparée et explicite.
