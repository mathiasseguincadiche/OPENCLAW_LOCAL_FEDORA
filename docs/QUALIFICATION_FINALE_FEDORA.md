# Qualification finale Fedora — résultats réels uniquement

Ce dossier distingue **précontrôle logiciel** et **réception sur le PC fixe**.
Les tests GitHub ne prouvent ni les performances de la B580, ni un appel
OpenRouter, ni la récupération d'une sauvegarde.

## 1. Précontrôle local sans mutation

Après l'installation, dans le dépôt et son environnement Python :

```bash
clawfedora-fedora-precheck \
  --root "$PWD" \
  --runtime-root "$OPENCLAW_LOCAL_FEDORA_ROOT"
```

Adapter la variable au chemin réel du runtime. Même si le rapport affiche
`READY_FOR_MANUAL_TESTS`, son verdict reste obligatoirement
`NOT_END_TO_END_QUALIFIED`. Il ne lit ni jetons, ni conversations,
ni détails de matériels ; seules les commandes systemd fixes (état **actif et activé au démarrage**)
et les deux sondes HTTP 127.0.0.1 sont consultées. Les sondes refusent toute
redirection, même depuis une URL locale : aucun suivi vers Internet. Ne pas utiliser ce rapport seul comme
preuve de fonctionnement.

## 2. Configuration Fedora et matériel

```bash
bash scripts/linux/07_health.sh
bash scripts/linux/04_check_hardware.sh system
bash scripts/linux/04_check_hardware.sh gpu
bash scripts/linux/13_openwebui.sh status
```

Noter les résultats réels de la B580, le pilote, l'AV1, la mémoire GPU,
le Wi-Fi, la stabilité de la veille (cinq cycles), les températures, le stockage
et l'affichage. Aucune prétention de validation de la B580 sans mesure locale.

## 2 bis. Benchmark B580 opt-in (aucune modification de configuration)

```bash
clawfedora-gpu-benchmark --root "$PWD"
clawfedora-gpu-benchmark --root "$PWD" --apply
# Réception exigeante uniquement sur la vraie B580, après préqualification :
clawfedora-gpu-benchmark --root "$PWD" --near-limit
clawfedora-gpu-benchmark --root "$PWD" --near-limit --apply
```

Cette commande teste 8K, 16K puis 32K de contexte via Ollama
**exclusivement local**, enregistre les tokens/s et la part VRAM et
propose le plus grand contexte entièrement sur GPU parmi les mesures,
mais **le profil normal ne remplit que 60 % du contexte : sa recommandation est provisoire**.
Le mode `--near-limit` sollicite environ 90 % du contexte et ne reconnaît
`qualified_near_limit_context` que si le serveur rapporte **au moins 80 % de tokens
entrants**, une allocation de contexte suffisante et un modèle totalement en VRAM.
Toute mesure tronquée, offload CPU ou preuve incomplète laisse ce champ vide.
Même un rapport favorable exige les tests de stabilité et une réception humaine
sur la vraie machine Fedora 45/B580.
Elle ne change **aucun** réglage. L'opérateur décide ensuite si 16K
est préférable à 32K ; aucune vitesse ou qualité ne peut être affirmée
sans les mesures sur la vraie B580.

## 3. Première installation WebUI 0.12.3 et réception navigateur

Le socle neuf installe directement **Open WebUI 0.12.3-slim**, sans migration
historique depuis 0.11.4. Le script `webui-install --apply` télécharge
l'image du tag stable, obtient son digest de registre et inscrit exclusivement
la référence `@sha256` dans l'unité systemd. Si aucun digest exploitable
n'est retourné, l'installation **échoue fermée**.

```bash
./menu.sh --action webui-install --apply
./menu.sh --action webui-status
```

Optionnel : un contrôle isolé sous Podman, sans modifier les données réelles,
peut être lancé avec `bash scripts/linux/14_webui_canary.sh --apply`.
`--with-db-copy` ne sert **que si une base préexistante est disponible** :
ce n'est pas un passage obligatoire pour une machine vierge.

Lors de la réception réelle, constater la connexion, la création du compte
administrateur unique, le verrouillage des inscriptions, les Functions/Filters,
les actions de projet, les uploads, les téléchargements, la voix et les
réponses du chat. Un test conteneur/SQLite de CI n'en prouve pas le bon
fonctionnement dans un navigateur Fedora. Le canary `--browser` exige
une base de test existante, utilise un réseau interne unique et publie
uniquement `127.0.0.1:3001`.

## 4. Streaming et contrôle d'accès

Suivre [la procédure SSE](STREAMING_SSE_PREPARATION.md). Avec le seul Mentor
Qwen local, enregistrer le début de la réponse, le premier fragment, la fin,
puis vérifier l'annulation, le verrou et l'absence de clé Gateway dans le
navigateur. Retirer le marqueur canary et contrôler que l'API opérateur est
de nouveau explicitement désactivée.

## 5. Compréhension réelle des images

Le chat libre conserve le mode métadonnées **par défaut**. La vision
PNG/JPEG/WEBP et PDF scanné sur 1 à 2 pages est désormais intégrée au code,
mais elle exige un marqueur privé d'activation. Lire
[VISION_LOCALE_CANARY.md](VISION_LOCALE_CANARY.md) avant de l'activer.

Pour éprouver les deux formats sans aucune donnée personnelle, lancer
le test **synthétique** en mode aperçu, puis après activation explicite :

```bash
clawfedora-vision-smoke --root "$PWD" --runtime-root /srv/openclaw-local
clawfedora-vision-smoke --root "$PWD" --runtime-root /srv/openclaw-local --apply
```

Le test génère localement un carré rouge sur fond blanc, puis un PDF d'une
page contenant la même image. Il utilise uniquement la route de vision
Qwen locale et exige les précontrôles du modèle et du worker. Une réponse
de Qwen **ne certifie pas l'exactitude de sa description** : vérifier
manuellement la forme et la couleur retournées et l'absence de cloud.

## 6. OpenRouter et coût

```bash
bash scripts/linux/14_cloud.sh status
```

Un appel réel doit faire l'objet d'un accord spécifique, d'une limite de clé
chez OpenRouter, d'un compte prépayé **sans recharge automatique**, puis d'un
contrôle de la facturation dans le plafond de 25 €/mois. Aucun contenu privé
n'est transmis sans consentement.

## 7. Sauvegarde et restauration

```bash
bash scripts/linux/08_backup_restore.sh backup
# Utiliser une archive identifiée et un dossier neuf hors production :
bash scripts/linux/08_backup_restore.sh restore ARCHIVE DESTINATION
```

La destination doit être vide et **différente du runtime actuel**.
Tester les empreintes, les permissions, le contenu et les données
de la copie restaurée. L'archive de l'atelier IA n'est **pas** un
backup de VM ou de disques QCOW2 ; cette validation ne couvre donc pas
les backing-files libvirt.

```bash
clawfedora-backup-verify /chemin/vers/sauvegarde.tar.gz
```

La commande restaure l'archive dans un répertoire temporaire privé, vérifie
les empreintes et les éventuelles bases SQLite (quick_check), puis supprime la
copie. Elle ne modifie pas le runtime actif et ne divulgue aucun nom de fichier
ni contenu. La CI effectue aussi une sauvegarde/restauration d'un runtime factice.

## 8. Qualité des artefacts

Ouvrir un vrai runbook PDF, DOCX et Draw.io : contrôler titres, tableaux,
pagination, blocs de code, accents, diagrammes multi-vues, liens, fichiers
source et manifeste SHA-256. L'inspection visuelle est obligatoire.

| Domaine | État initial |
|---|---|
| Fedora / B580 / veille / AV1 | Non qualifié sur la machine |
| Open WebUI 0.12.3 / nouveau volume / navigateur | Canary logiciel, essai réel manquant |
| Streaming SSE / annulation | Code intégré, essai réel manquant |
| Vision des images et PDF scannés | Code canary intégré, précision et performances B580 non qualifiées |
| OpenRouter / coût réel | Essai avec accord manquant |
| Archive et restauration sur copie | Essai local manquant |
| Inspection PDF / DOCX / Draw.io | Essai visuel manquant |

## 9. Réception de Fedora 45 Workstation / GNOME 51

Le **système hôte unique** de la première installation est Fedora 45
Workstation, GNOME Shell 51 sous Wayland. Fedora 44 et GNOME 50 sont
refusés par le bootstrap, la configuration WebUI et le contrôle matériel.

La CI exécute les tests sous un conteneur Fedora 45
(`fedora-45-contract`) et vérifie qu'une installation sous Fedora 44
est refusée (`fedora-44-rejection`). Au **14 octobre 2026**, l'image Fedora
45 disponible est encore une version de développement/bêta. Cette CI
valide le code et la cohérence des dépendances Python dans ce conteneur ;
elle ne simule **ni GNOME Shell graphique, ni SELinux/Podman complets, ni
la B580 et ses pilotes**.

**Attendre la publication Fedora 45 stable**, actuellement visée le
**20 octobre 2026** (date susceptible de report), puis tester sur le
vrai poste le noyau/Mesa, GNOME 51/Wayland, le driver `xe`, Resizable
BAR, les services et la veille/reprise. Ne conclure **QUALIFIÉ** qu'après
des preuves datées pour chaque domaine. Ne jamais stocker de clé,
jeton, conversation privée ou secret dans le dossier de preuves.
