# Préqualification de Fedora 45 sur clé Live USB (avant installation)

[← Documentation](README.md) · [Audit du code](AUDIT_SOURCE_2026_10_27.md) · [État](../STATUS.md)

## Ce que cet essai peut valider

**Première étape prévue : essayer Fedora sur la machine depuis la clé Live.**
Le programme ci-dessous observe le matériel ; il ne lance pas OpenClaw, Qwen et Open WebUI.
Il n'existe pas, dans cette version, de procédure qualifiée pour tester tout l'atelier
sur une simple Live USB sans installation. Ne pas remplacer ce contrôle par
`install --apply` dans l'espoir d'obtenir un essai temporaire équivalent : l'installateur
configure des services, des comptes et un runtime persistant sur `/data/IA/Openclaw/`.

Pour un essai complet avant de remplacer le système actuel, une installation Fedora
sur un support dédié serait une campagne distincte, avec stockage et démarrage à
préparer et à vérifier. Ce document ne fournit pas de recette d'installation sur les SSD internes.

**Information vérifiée le 27 octobre 2026 :** la réunion officielle du 22 octobre a
refusé la publication finale de Fedora 45 et déplacé la cible au **3 novembre 2026**,
sous réserve d'une nouvelle décision. Une image RC/bêta peut servir à observer le matériel,
mais ne permet pas de qualifier la version stable finale visée ici. Voir le
[compte rendu officiel](https://meetbot.fedoraproject.org/meeting_matrix_fedoraproject-org/2026-10-22/f45-final-go-no-go-meeting.2026-10-22-17.00.html)
et la [page de téléchargement Workstation](https://fedoraproject.org/workstation/download/).

## Objectif

Vérifier la compatibilité **matérielle** de la tour avec Fedora 45 Workstation /
GNOME Shell 51 / Wayland **sans modifier l'installation actuelle**.

Le contrôle Live est volontairement distinct de :
- `scripts/linux/00_bootstrap.sh --apply` (installation de paquets et configuration hôte) ;
- `scripts/linux/13_openwebui.sh install --apply` (déploiement Podman) ;
- `clawfedora-fedora-precheck` (sonde des services installés, inutilisable comme
  validation d'une session Live vierge) ;
- `clawfedora-gpu-benchmark --apply` (nécessite Ollama et le modèle installés).

**Aucun de ces quatre programmes ne doit être lancé avec `--apply` durant
la préqualification Live.** Le script Live refuse l'exécution avec sudo/root,
n'installe aucun paquet, ne monte ou formate aucun disque, ne contacte aucun
fournisseur cloud et ne collecte aucune clé ou conversation.

### Prérequis

1. Attendre la publication **officielle finale** de Fedora 45 Workstation ;
   vérifier la disponibilité sur le site officiel au moment du téléchargement.
2. Télécharger l'ISO Workstation officielle, en vérifier l'empreinte et la
   signature comme recommandé par Fedora, puis la graver avec Fedora Media
   Writer. Vérifier soigneusement la clé USB cible **lors de sa création**.
3. Faire une sauvegarde de l'installation actuelle avant de préparer toute
   installation définitive. Le mode Live ne remplace pas cette sauvegarde.
4. Dans le menu de démarrage UEFI, choisir la clé USB et lancer **« Essayer
   Fedora » / « Try Fedora »**, **sans** cliquer « Installer Fedora ».
5. Utiliser une session GNOME Wayland standard. Ne pas monter volontairement
   les partitions des SSD internes en lecture/écriture.

### Lancer le contrôle autonome (sans sudo)

Le dépôt est public. Dans un terminal de la session Live, avec connexion
Internet disponible :

```bash
git clone --depth 1 https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA \
  /tmp/clawfedora-live
cd /tmp/clawfedora-live
bash scripts/linux/16_live_usb_preflight.sh
```

Si `git` ou Internet est indisponible sur la session Live, **copier le
dépôt sur un média amovible depuis un autre ordinateur** puis exécuter
la même commande Bash dans ce dossier. Ne pas installer un gestionnaire
de paquets simplement pour lancer l'audit.

Rapport JSON synthétique (sans numéros de série/SSID/UUID ni sortie brute des
commandes ; seule la session Live peut posséder une copie temporaire) :

```bash
bash scripts/linux/16_live_usb_preflight.sh --json > /tmp/clawfedora-live-report.json
```

Le chemin `/tmp` correspond à l'environnement temporaire de la Live.
Il ne garantit **pas** que le rapport survit au redémarrage. Pour le conserver,
copier **explicitement** ce fichier vers une **seconde clé USB de données**,
après vérification de la destination. Ne jamais demander au script de l'écrire
sur un SSD interne.

### Résultats possibles

| Champ | Sens |
| --- | --- |
| `PASS` | Critère détectable confirmé **pour la session Live** |
| `REVIEW` | Outil indisponible ou observation non concluante |
| `FAIL` | Critère explicitement non satisfait |
| `PRECHECK=BLOCKED` | Au moins une vérification critique est absente ou en échec |
| `PRECHECK=READY_FOR_MANUAL_REVIEW` | Précontrôles critiques satisfaits, revue humaine encore requise |
| `INSTALLATION_AUTHORIZED=false` | Toujours présent ; le script **ne donne jamais un feu vert automatique** |

Critères critiques : vrai démarrage Live, Fedora 45 Workstation hors bêta
apparente, UEFI, GNOME 51, Wayland, identification Intel Arc B580 (ID PCI
`8086:e20b`), et pilote noyau `xe` associé à **cette** carte. Les
observations secondaires couvrent Vulkan, SELinux, RAM, réseau, audio et
présence des disques en **lecture seule par les commandes d'observation**.

La détection d'une version « finale » dans `/etc/os-release` **ne prouve pas
l'origine officielle de l'ISO** : l'empreinte et la signature doivent être
vérifiées séparément. L'outil ne promet pas qu'un programme autre que lui,
le bureau Live ou le firmware ne modifie jamais les SSD : ne pas monter les
volumes de l'installation précédente.

### Essais manuels dans la session Live

| Composant | Opération | Preuve attendue |
| --- | --- | --- |
| Affichage B580 | Tester les écrans, leur fréquence, couleurs, mode clair/blanc | Pas d'artefact ou de perte d'affichage |
| Réseau | Tester Ethernet, Wi-Fi, Bluetooth et reconnexion | Liaison stable, Internet réellement accessible |
| Son | Lecture audio, micro et périphériques USB | Lecture et capture réellement audibles |
| Vidéo/AV1 | Lire un média AV1 local et inspecter le décodage matériel si outillage présent | Fonctionnement réel, pas seulement détection GPU |
| Stockage | Voir les disques dans l'outil de partitionnement **sans modifier** | Inventaire cohérent ; aucune mutation |
| Veille/reprise | Faire un premier cycle manuellement avec la session Live | Affichage, réseau et USB fonctionnels après réveil |
| Stabilité | Session prolongée, consultation des erreurs visibles | Aucun gel/plantage notable |

La **série de cinq cycles veille/reprise** et les essais prolongés doivent
être répétés sur Fedora **installé** : la Live USB ne reproduit pas
fidèlement la gestion des services, le stockage, les mises à jour ou la
persistance de l'OS final.

### Après cette étape

Si les critères critiques sont validés **et que les essais manuels sont
acceptables**, préparer la sauvegarde externe, les partitions et la
procédure d'installation de Fedora 45. Le choix de procéder à l'installation
reste explicitement humain ; le script n'exécute pas l'installateur.

Après installation, consulter
[Qualification finale Fedora](QUALIFICATION_FINALE_FEDORA.md) :
- vérifier SELinux, pilotes, services et modules persistants ;
- installer OpenClaw, Ollama et Open WebUI via le runbook standard ;
- tester la B580 à 8K/16K/32K (mode `--near-limit` pour la vraie capacité) ;
- vérifier sept agents, projets 1–4, SSE, voix, cloud optionnel à budget borné ;
- pratiquer la sauvegarde/restauration réelle dans un dossier distinct.

**Statut final jusqu'à cette réception :** `NOT_INSTALLED_NOT_END_TO_END_QUALIFIED`.
Un résultat vert sur une clé Live signifie seulement **matériel
préqualifié**, jamais « 10/10 en production ».
