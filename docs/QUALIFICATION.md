# Qualification Fedora

## Principe

La qualification Fedora reprend le contrat HARD-40M du projet Windows afin de conserver une comparaison utile :

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

Cette matrice sera importée avec le cœur benchmark lorsque M1 sera terminé.

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
- paquets Mesa/Intel ;
- version OpenClaw ;
- version Ollama ;
- commit llama.cpp ;
- digest/quantification des trois modèles ;
- état ReBAR ;
- RAM/VRAM ;
- backend exact.

## Ordre des campagnes

1. Fedora kernel officiel + Ollama Vulkan ;
2. Fedora kernel officiel + llama.cpp Vulkan ;
3. Fedora kernel officiel + llama.cpp SYCL ;
4. kernel 7.2.3 + meilleur(s) backend(s) ;
5. confirmation par 3 runs du candidat gagnant.

## Critère Fedora vs Windows

Objectif de migration :

- ≥ 10 % de gain agrégé cible ;
- aucune régression fonctionnelle ou sécurité ;
- aucune régression > 5 % sur un modèle ;
- E2E OpenClaw et tool calling PASS ;
- Golden Projects PASS ;
- projet représentatif PASS.

Un gain inférieur à 10 % ne rend pas automatiquement Fedora mauvais : les bénéfices d'exploitation (systemd, KVM, Podman, Linux natif) peuvent être évalués séparément. En revanche, le dépôt ne revendiquera pas l'objectif « performance supérieure » sans preuve chiffrée.

## Promotion

Aucune promotion automatique de backend, kernel ou V1. Les fichiers de résultat proposent un candidat ; l'opérateur décide après lecture des preuves.
