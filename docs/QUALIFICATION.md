# Qualification Fedora

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
L6 runtimes + kernel + Gemma ↔ Ministral
        ↓
L7 Golden Projects + projet représentatif
        ↓
L8 Release Readiness
        ↓
Approbation humaine explicite
```

Aucun gate matériel n'est déclaré PASS par la CI. La CI valide le protocole, les contrats, les tests, les DryRun et le comportement fail-closed. Les verdicts L2 à L6 doivent être produits sur la machine cible. L7 peut être validé logiciellement en CI, mais doit être rejoué sur l'installation finale avant L8.

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

SYCL/Level Zero n'est pas requis par L3 : il reste un candidat L6 optionnel.

## L4 — OpenClaw E2E

DryRun :

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
- 3 probes Qwen avec reasoning natif ;
- plafond absolu de 768 tokens par scénario, avec 768 tokens sur les probes Qwen dédiés ;
- 210 s max par cas ;
- **2400 s / 40 min max pour le gate complet**, préflight et évaluation inclus ;
- endpoint Ollama loopback uniquement ;
- aucun appel cloud ;
- aucun téléchargement implicite de modèle ;
- identité exacte digest + quantification des trois modèles ;
- kernel, Mesa et version Ollama enregistrés ;
- aucune promotion automatique.

### DryRun

```bash
./menu.sh --action qualification-dry-run
```

Le DryRun valide la matrice et les contrats sans contacter Ollama ni le matériel.

### Profil performance

Le run réel exige un profil performance reproductible. Vérification sans modification :

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

L'entrée CLI réelle refuse L5 si le marqueur du launcher protégé n'est pas présent et revalide les contrats HARD-40M avant tout accès au matériel ou à Ollama. Un fichier suite hors contrat ne peut donc pas contourner les limites en lançant directement la CLI.

## Seuils L5

Le gate reste exigeant :

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

Les preuves L2/L3 restent toujours sous `proofs/hardware/`, y compris lorsqu'elles sont produites comme préflight d'un run HARD-40M. La preuve HARD-40M référence leurs chemins canoniques.

Les preuves HARD-40M et L6 ne stockent pas la sortie brute des modèles : elles conservent les SHA-256, longueurs/checks nécessaires, métriques, identités modèles et versions runtime.

## L6 — Comparaisons Linux

Après un L5 baseline PASS :

1. kernel Fedora officiel + Ollama Vulkan ;
2. kernel Fedora officiel + llama.cpp Vulkan ;
3. kernel Fedora officiel + llama.cpp SYCL/Level Zero, si le candidat est installé ;
4. kernel 7.2.3 + runtime retenu pour comparaison ;
5. Gemma 3 12B vs Ministral 3 14B sur le même slot `gemma-deep` ;
6. confirmation par 3 runs par série avant toute décision.

Une seule variable change à la fois. Un candidat optionnel absent ne rend jamais la baseline invalide.

### Challenger Ministral — hors routage

Le provisionnement nominal `models` reste limité aux trois modèles routés. Ministral utilise un chemin distinct :

```bash
./menu.sh --action challenger-model
```

Ce DryRun affiche le modèle mais ne télécharge rien. Provisionnement explicite :

```bash
./menu.sh --action challenger-model --apply
```

La commande appelle uniquement `ollama pull ministral-3:14b-instruct-2512-q4_K_M`. Elle ne modifie pas le routeur et ne compte jamais Ministral comme quatrième modèle nominal.

Chaque série Gemma/Ministral se collecte séparément :

```bash
clawfedora-l6 --runtime-root /srv/openclaw-local snapshot-challenger \
  --variant incumbent \
  --output /srv/openclaw-local/proofs/l6/challenger/gemma-run-1.json

clawfedora-l6 --runtime-root /srv/openclaw-local snapshot-challenger \
  --variant challenger \
  --output /srv/openclaw-local/proofs/l6/challenger/ministral-run-1.json
```

Répéter trois fois chaque variante. Le runner utilise le même corpus de trois probes :

- extraction documentaire structurée ;
- tool-calling `record_incident` avec arguments exacts ;
- vision sur fixture PNG locale.

Il enregistre `vision_pass`, `document_quality_pass`, `tool_calling_pass`, performances, identité/digest et hash des sorties, sans persister les sorties brutes.

La comparaison :

```bash
clawfedora-l6 compare-challenger \
  --baseline /srv/openclaw-local/proofs/l6/challenger/gemma-run-1.json \
  --baseline /srv/openclaw-local/proofs/l6/challenger/gemma-run-2.json \
  --baseline /srv/openclaw-local/proofs/l6/challenger/gemma-run-3.json \
  --candidate /srv/openclaw-local/proofs/l6/challenger/ministral-run-1.json \
  --candidate /srv/openclaw-local/proofs/l6/challenger/ministral-run-2.json \
  --candidate /srv/openclaw-local/proofs/l6/challenger/ministral-run-3.json \
  --output /srv/openclaw-local/proofs/l6/decisions/ministral.json
```

Un résultat `ELIGIBLE_FOR_HUMAN_PROMOTION` n'effectue aucune promotion. Il signifie seulement que Ministral peut être proposé pour remplacer Gemma après décision humaine distincte.

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
- exige les trois décisions L6 obligatoires : llama.cpp Vulkan, kernel 7.2.3 et Gemma ↔ Ministral ;
- recharge les snapshots et **recalcule** les décisions L6 avec les contrats courants ;
- exige L7 PASS avec six projets en `PACKAGING` et gate humain préservé ;
- produit un manifeste SHA-256 de toutes les preuves retenues.

Le résultat est uniquement `BLOCKED` ou `READY_FOR_HUMAN_REVIEW`. Même READY, V1 reste non approuvée.

## Approbation humaine L8

L'approbation n'est volontairement pas une action du menu. Elle nécessite une commande explicite :

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
