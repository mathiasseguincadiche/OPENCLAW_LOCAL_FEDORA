# Laboratoire DevOps hors ligne — préparation des validations réelles

[← Guide](GUIDE.md) · [Rôles](fiches/07-roles-et-outils.md) · [Plan de qualité](PLAN_QUALITE_2026.md)

## Pourquoi ce module existe

Aujourd'hui, l'agent DevOps **rédige** Terraform, Ansible, Bash ou GitHub Actions ; ses outils intégrés **n'exécutent pas** `terraform validate`, `ansible-lint` ou `actionlint`. Le laboratoire est une première étape vers une **preuve technique authentique** sans donner un terminal à Qwen ni à DeepSeek.

La nouvelle commande `clawfedora-lab` est **indépendante des agents et d'Open WebUI** : **seul l'utilisateur** peut déclencher le contrôle avec `--apply`. Elle exécute un validateur statique précis dans un conteneur **Podman rootless**, sur une **copie temporaire limitée du projet**, avec réseau désactivé.

> **Ce qui est prêt :** moteur CLI, restriction des arguments, collecte défensive, vérifications d'isolation testées en CI.
> **Ce qui manque :** une image de laboratoire Rocky Linux *construite et qualifiée*, avec les outils souhaités et les versions épinglées, puis des tests en vrai Podman sur le PC. Le code **n'installe aucun outil**, **ne construit pas d'image** et **ne certifie pas que les validateurs existent** dans l'image fournie.

## Fonctionnement concret

```text
                   Confirmation utilisateur --apply
                                   │
Dossier original ── lecture bornée ──► Copie temporaire sans liens ni secrets connus
                                   │
                       Podman rootless + image @sha256
                    réseau NONE · FS en lecture seule
                     CPU/mémoire/processus plafonnés
                                   │
                   Commande de validation autorisée
                                   │
                         PASS / FAIL / REFUSED
                           Journaux affichés
                                   │
                    Copie et conteneur supprimés
```

Il ne s'agit **pas** d'une VM Rocky Linux complète. L'image OCI choisie doit provenir d'une construction contrôlée — par exemple basée sur Rocky avec uniquement les validateurs requis. Le fait qu'une image soit référencée par digest **garantit son identité**, pas sa confiance ni sa provenance ; il faut donc aussi vérifier son origine et son contenu.

## Premier essai — sans exécuter quoi que ce soit

Après installation du projet en environnement Python :

```bash
clawfedora-lab --project /chemin/vers/projet --tool terraform-fmt
clawfedora-lab --project /chemin/vers/projet --tool ansible-lint
```

Ce **dry-run** ne demande pas Podman et ne lance aucun validateur. Il annonce seulement les fichiers sélectionnés et les contrôles prévus.

Pour une **exécution réelle**, l'utilisateur doit disposer localement d'une image de validateurs **épinglée par digest** (aucun tag mutable) :

```bash
clawfedora-lab \
  --project /chemin/vers/projet \
  --tool terraform-fmt \
  --image 'registry.example.org/rocky-validators@sha256:<EMPREINTE_REELLE_64_HEX>' \
  --apply
```

La référence ci-dessus est volontairement **un emplacement fictif** : elle n'est pas une image disponible. Ne l'utilise pas telle quelle ; récupère le digest **réel** de l'image préalablement construite, inspectée et présente dans Podman. La commande refuse les images absentes plutôt que de les télécharger automatiquement.

## Quels contrôles sont prévus ?

| `--tool` | Vérification tentée à l'intérieur de l'image | Ce que cela ne prouve pas |
|---|---|---|
| `terraform-fmt` | `terraform fmt -check -recursive -no-color` | Ressources cloud créées ou utilisables |
| `terraform-validate` | `terraform validate -no-color` | Backend, providers, modules externes chargés (hors ligne) ou `apply` réussi |
| `ansible-lint` | `ansible-lint --offline` | Playbook exécuté ou idempotence sur Rocky |
| `actionlint` | Validation des workflows sous `.github/workflows/` | GitHub Actions réellement exécuté |
| `shellcheck` | Analyse statique des scripts `.sh` de la copie | Shell script sans défaut métier |
| `hadolint` | Analyse des `Dockerfile` | Conteneur construit, signé ou démarré |

Tous les binaires doivent **déjà exister dans l'image**. Si un outil manque, le contrôle échoue ; aucun PASS n'est inventé. Pour `terraform validate`, les dépendances nécessaires doivent être préparées **dans l'image ou l'instantané approuvé** : la politique hors ligne ne doit jamais être contournée pour obtenir une réussite.

## Protections intégrées

- **Aucun accès direct des agents** à cette commande : ni API d'exécution libre, ni outil OpenClaw supplémentaire.
- **`--apply` requis** ; refus si l'utilisateur est root.
- Image OCI locale immuable par `@sha256`, **aucun pull automatique**.
- **`--network=none`**, aucun proxy HTTP, **`--read-only`**, capacités supprimées, `no-new-privileges`, UID rootless et quotas.
- **Pas de montage du dossier original** : seuls des fichiers source non liés, limités à 300 fichiers et 12 Mio, passent dans une copie temporaire. Le relabel SELinux `:Z` ne touche **que cette copie**.
- Refus des fichiers connus comme sensibles (fichiers `.env`, `.tfvars`, `.tfstate`, clés privées). Il ne s'agit **pas** d'un détecteur parfait de données confidentielles : vérifier le dossier avant `--apply`.
- Commandes et arguments fixés dans le code, sans `shell=True`, aucun script fourni par un modèle exécuté directement.
- Échec explicite si image absente, source trop volumineuse, lien symbolique, outil inconnu, binaire manquant ou durée dépassée.

## Pourquoi ne pas exposer directement cet outil aux agents ?

Parce que même une validation présentée comme inoffensive peut charger des plugins, exécuter des vérifications externes ou traiter du code hostile. La bonne architecture est : **copie jetable → image contrôlée → sortie de commande → rapport interprété par l'IA**, avec consentement avant toute action.

Le raccordement ultérieur à l'Atelier Projets devra passer par une **file d'approbation déterministe**, jamais par un argument de commande généré librement par le modèle. L'exécution de playbooks Ansible ou d'un `terraform apply` réel appartient à un lot distinct, avec environnement jetable et autorisation dédiée.

## Phase de tests matériels, à la fin

Pour atteindre le niveau « prêt quotidien » :
1. produire et contrôler l'image Rocky des validateurs, ses versions et son digest ;
2. exécuter les six scénarios réels sous Fedora/Podman rootless, SELinux Enforcing ;
3. tenter les refus : secret, lien symbolique, timeout, image absente, outil absent, projet volumineux ;
4. vérifier qu'aucun fichier source original n'a changé ;
5. conserver les journaux assainis reliés au bon commit du projet ;
6. intégrer les résultats au rapport de l'Atelier Projets **seulement après** validation.

**Verdict actuel : exécuteur de validations offline préparé dans le dépôt, qualification réelle restant à faire.**
