# Qualification Fedora

## Principe

La qualification HARD-40M est un gate natif Fedora :

- 3 modèles obligatoires ;
- 30 cas ;
- 24 cas à 8K ;
- 6 cas à 16K ;
- 3 probes Qwen avec reasoning natif ;
- 768 tokens max sur ces probes ;
- 210 s max par cas ;
- 2400 s max pour le gate complet ;
- aucun appel cloud ;
- aucun téléchargement implicite de modèle.

## Avant HARD-40M

Le host doit passer :

```bash
./menu.sh --action validate
./menu.sh --action audit-strict
./menu.sh --action gpu
```

Puis doivent être enregistrés :

- commit du dépôt ;
- `uname -r` ;
- version Mesa ;
- version OpenClaw ;
- version Ollama ;
- commit llama.cpp ;
- digest/quantification des trois modèles ;
- état ReBAR ;
- RAM/VRAM ;
- runtime exact ;
- versions de la pile accélérateur optionnelle lorsqu'elle est activée.

## Ordre des campagnes

1. kernel Fedora officiel + Ollama Vulkan ;
2. kernel Fedora officiel + llama.cpp Vulkan ;
3. kernel Fedora officiel + llama.cpp SYCL/Level Zero, si le candidat est installé ;
4. kernel 7.2.3 + runtime gagnant ;
5. confirmation par 3 runs du candidat gagnant.

Une seule variable change à la fois. Un candidat optionnel absent ne rend jamais la baseline invalide.

## Critère d'optimisation Linux

Baseline : **kernel Fedora officiel + Ollama Vulkan**.

Objectif :

- ≥ 10 % de gain agrégé cible pour une configuration optimisée ;
- aucune régression fonctionnelle ou sécurité ;
- aucune régression > 5 % sur un modèle ;
- E2E OpenClaw et tool calling PASS ;
- Golden Projects PASS ;
- projet représentatif PASS.

Un gain inférieur à 10 % n'est pas maquillé en succès. Le projet conserve alors la configuration la plus stable et documente les résultats réels.

## Promotion

Aucune promotion automatique de runtime, kernel ou V1. Les fichiers de résultat proposent un candidat ; l'opérateur décide après lecture des preuves.
