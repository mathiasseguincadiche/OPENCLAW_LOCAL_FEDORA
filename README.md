# Atelier IA hybride — Infrastructure & OPS

<p align="center"><img src=".github/social-preview.svg" alt="Atelier IA Fedora : Qwen local, DeepSeek cloud facultatif et sept rôles OpenClaw" width="100%"></p>

[![CI](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/ci.yml)
[![CodeQL](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/workflows/codeql.yml)
[![Fedora 45](https://img.shields.io/badge/Fedora-45-51A2DA?logo=fedora&logoColor=white)](https://fedoraproject.org/)
[![Licence MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)

**Un atelier IA personnel pour apprendre, préparer et documenter des projets DevOps sur Fedora.** OpenClaw organise sept rôles autour de **Qwen 3.5 9B local**. **DeepSeek via OpenRouter** apporte une route cloud facultative, sur autorisation explicite.

[Découvrir](docs/GUIDE.md) · [Tester en Live USB](docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md) · [Installer](docs/INSTALLATION_SIMPLE_FEDORA45.md) · [Documentation](docs/README.md) · [État du projet](STATUS.md)

> **En qualification : le PC cible reste à valider.** L'audit du 27 octobre relève des corrections à réaliser avant un usage quotidien. Le projet n'a pas encore tourné sur le PC dans le cadre de cette réception. [Constats et priorités](docs/AUDIT_SOURCE_2026_10_27.md).

## Ce que tu peux faire

- **Discuter et apprendre** : poser une question ou analyser de petits fichiers sans créer de projet.
- **Préparer une infrastructure** : architectures, configurations, scripts, runbooks et points de contrôle.
- **Organiser un projet** : sources, plan, tâches, validations humaines et livrables persistants.
- **Rédiger et vérifier** : Markdown, exports PDF/DOCX/ODT, schémas Draw.io et audits de cohérence.

L'IA explique et propose. Les actions sensibles et la livraison restent soumises à ta validation ; l'atelier ne déploie pas automatiquement l'infrastructure préparée.

## Trois façons de travailler

| Interface | Usage |
| --- | --- |
| **Open WebUI 0.12.3** — `http://127.0.0.1:3000` | Le chat : rôles, pièces jointes et six raccourcis pour les projets |
| **Atelier Projets** — `http://127.0.0.1:18890` | Les sources, étapes, décisions et livrables |
| **Terminal** — `./menu.sh` | Installation, contrôles, services et maintenance ; [CLI des projets](docs/fiches/04-atelier-projets.md#en-ligne-de-commande) |

Les projets restent indépendants. Une seule génération utilise le moteur à la fois. Le chat répond en un bloc par défaut ; le streaming reste expérimental.

## Commencer

### 1. Essayer Fedora sur la machine

Le premier essai prévu utilise **Fedora 45 Workstation / GNOME 51 / Wayland en Live USB**. Le contrôle autonome observe le matériel sans installer l'atelier :

```bash
# Depuis une copie du dépôt dans la session Live, sans sudo
bash scripts/linux/16_live_usb_preflight.sh
```

Suivre le [guide Live USB](docs/LIVE_USB_FEDORA45_PREQUALIFICATION.md) pour préparer le média et conserver le rapport. **Un résultat favorable préqualifie le matériel ; il ne valide pas encore OpenClaw, Qwen ou WebUI.** La date de publication de Fedora doit être vérifiée sur le site officiel avant de choisir l'ISO.

### 2. Installer l'atelier

Sur Fedora installé, suivre le [guide d'installation](docs/INSTALLATION_SIMPLE_FEDORA45.md), qui regroupe la préparation du stockage, le précontrôle, l'installation et la création du compte WebUI. Le runtime et ses projets utilisent **`/data/IA/Openclaw/`**, sur le disque secondaire EXT4.

Après installation et configuration de WebUI, depuis le dépôt :

```bash
./menu.sh --action quick-check
```

Si le contrôle affiche `RECEPTION=READY_FOR_FIRST_PROJECT`, poser une vraie question dans WebUI et créer un petit projet de test. Les défauts ouverts et les critères de réception restent indiqués dans [STATUS](STATUS.md).

**Machine cible :** Ryzen 7 7700, 48 Go de RAM, Intel Arc B580 12 Go. Fedora est le système hôte du projet IA ; Open WebUI tourne sous Podman rootless sur ce même Fedora. Aucune installation de Rocky Linux n'est nécessaire. [Stockage et prérequis](docs/STOCKAGE_DATA.md).

## Local au quotidien, cloud sur décision

Qwen travaille sur la machine avec Ollama. DeepSeek V4.1 Flash 1017 constitue une option pour les dossiers complexes : aucun repli automatique du local vers le cloud. L'activation, les accords de projet et le budget sont contrôlés par la passerelle locale ; le plafond configuré est de **25 €/mois**, à compléter par une limite fournisseur et du prépaiement.

Une recherche Web peut contacter Internet même avec Qwen local. Le [mode Web privé](docs/WEB_ACCESS_PRIVATE_MODE.md) désactive ces outils. Le filtre de confidentialité reste une aide ; il ne garantit pas qu'un contenu autorisé pour le cloud soit publiable.

[Comprendre les deux routes](docs/ARCHITECTURE_HYBRIDE.md) · [Activer le cloud](docs/fiches/12-cloud.md) · [Sécurité](SECURITY.md)

## Sept rôles, un même atelier

Mentor infrastructure/OPS · Expert recherche · Architecte solutions · Ingénieur DevOps · Ingénieur sécurité · Rédacteur pédagogique · Auditeur qualité.

Chaque rôle reçoit ses consignes et ses outils autorisés. [Découvrir leurs responsabilités](docs/fiches/07-roles-et-outils.md) · [Voir l'architecture](docs/fiches/11-comment-ca-marche.md).

## Documentation

| Besoin | Guide |
| --- | --- |
| Prendre en main le chat et les projets | [Discussion](docs/fiches/03-discuter.md) · [Atelier Projets](docs/fiches/04-atelier-projets.md) |
| Produire ou importer des documents | [Fichiers, exports et schémas](docs/fiches/06-fichiers-et-schemas.md) |
| Juger la qualité des explications | [Évaluation pédagogique](docs/EVALUATION_PEDAGOGIE.md) |
| Diagnostiquer ou préparer la réception | [Dépannage](docs/fiches/10-depanner.md) · [Validation](docs/validation/README.md) |
| Comprendre les versions et protections | [Références techniques](docs/reference/README.md) · [État et limites](STATUS.md) |

[Contribuer](CONTRIBUTING.md) · [Historique](CHANGELOG.md) · [Licence MIT](LICENSE)
