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
L6 comparaison des candidats Linux
```

Aucun gate matériel n'est déclaré PASS par la CI. La CI ne valide que le protocole, les contrats,
les tests et les DryRun. Les verdicts L2 à L6 doivent être produits sur la machine cible.

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

Le run réel est protégé contre la suspension par `systemd-inhibit`.

## L5 — HARD-40M

Contrat :

- 3 modèles obligatoires ;
- exactement 30 cas ;
- 24 cas à 8K ;
- 6 cas à 16K ;
- 12 scénarios couverts collectivement à 8K ;
- 10 cas par modèle ;
- 3 probes Qwen avec reasoning natif ;
- 768 tokens max sur ces probes ;
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

Le launcher utilise `systemd-inhibit --what=sleep --mode=block`. Le runner démarre son chronomètre
avant L2/L3 et réduit automatiquement le budget benchmark du temps déjà consommé. Il ne peut donc
pas dépasser volontairement la limite de 2400 secondes.

## Seuils L5

Le gate reste exigeant :

- taux d'erreur maximum : `0.0` ;
- taux de checks minimum : `0.875` ;
- médiane minimale : `6.0 tok/s` ;
- p95 premier token maximum : `12000 ms` ;
- 8K : au moins `0.875` de checks PASS ;
- 16K : au moins `0.75` de checks PASS.

Une sortie tronquée, une erreur API ou un timeout de cas déclenche un fail-fast, car le taux
d'erreur autorisé est nul.

## Preuves

Les preuves ne sont pas versionnées dans Git. Elles sont stockées sous la racine runtime :

```text
/srv/openclaw-local/proofs/
├── hardware/
├── openclaw-e2e/
└── qualification/
```

Les preuves HARD-40M ne stockent pas la sortie brute des modèles : elles conservent le SHA-256,
la longueur, les checks, les métriques, les identités modèles et les versions runtime.

## Ordre des campagnes L6

Après un L5 baseline PASS :

1. kernel Fedora officiel + Ollama Vulkan ;
2. kernel Fedora officiel + llama.cpp Vulkan ;
3. kernel Fedora officiel + llama.cpp SYCL/Level Zero, si le candidat est installé ;
4. kernel 7.2.3 + runtime gagnant ;
5. confirmation par 3 runs du candidat gagnant.

Une seule variable change à la fois. Un candidat optionnel absent ne rend jamais la baseline invalide.

## Promotion

Aucune promotion automatique de backend, kernel ou V1. Une preuve PASS rend seulement la
configuration éligible à la revue humaine et aux gates suivants.
