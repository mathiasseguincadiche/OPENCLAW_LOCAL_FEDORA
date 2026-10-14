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
```

Cette commande teste 8K, 16K puis 32K de contexte via Ollama
**exclusivement local**, enregistre les tokens/s et la part VRAM et
propose le plus grand contexte entièrement sur GPU parmi les mesures.
Elle ne change **aucun** réglage. L'opérateur décide ensuite si 16K
est préférable à 32K ; aucune vitesse ou qualité ne peut être affirmée
sans les mesures sur la vraie B580.

## 3. Migration Open WebUI 0.12 sans bascule de production

```bash
bash scripts/linux/14_webui_canary.sh
bash scripts/linux/14_webui_canary.sh --apply --with-db-copy
# Facultatif, dans un vrai terminal pour tester également l'interface :
bash scripts/linux/14_webui_canary.sh --apply --with-db-copy --browser
```

Sur l'état WebUI, l'audit vérifie désormais non seulement les comptages
de lignes mais aussi la conservation des identifiants et des contenus JSON
des conversations à empreintes SHA-256 privées, et refuse une Function modifiée.
Ces preuves ne remplacent **pas** les essais visuels : connexion, rôles,
actions, uploads, téléchargement, voix, annulation et préservation des sessions
dans un vrai navigateur restent à constater manuellement sur Fedora.
Le mode `--browser` publie **uniquement** `127.0.0.1:3001` depuis
un réseau Podman interne isolé et désactive les fournisseurs OpenAI/Ollama.
La copie de base et le conteneur sont supprimés dès que l'opérateur appuie
sur Entrée dans le terminal. Ce mode ne remplace pas le véritable Open WebUI
de production ni un test complet des fonctions reliées à la passerelle.

Le canary doit afficher le digest exact de l'image téléchargée, vérifier
la santé conteneur, le schéma SQLite, les utilisateurs, conversations et
Functions sur une **copie**. Aucun volume principal n'est modifié.
Tester ensuite **dans un navigateur isolé** login, modèles, actions de projet,
pièces jointes, téléchargements et voix. L'épinglage de production reste
v0.11.4 jusqu'à validation distincte de tous les résultats.

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
| Open WebUI 0.12 / copie SQLite / navigateur | Canary logiciel, essai réel manquant |
| Streaming SSE / annulation | Code intégré, essai réel manquant |
| Vision des images et PDF scannés | Code canary intégré, précision et performances B580 non qualifiées |
| OpenRouter / coût réel | Essai avec accord manquant |
| Archive et restauration sur copie | Essai local manquant |
| Inspection PDF / DOCX / Draw.io | Essai visuel manquant |

## 9. Fedora 45 bêta, sans promotion de production

La CI contient désormais un job `fedora-45-preview` utilisant une
image de Fedora 45 pour exécuter les contrats et les tests Python. La
distribution était en **bêta au 12 octobre 2026** : le bootstrap du PC reste
volontairement restreint à Fedora 44 jusqu'aux tests matériels GNOME 51,
Intel B580, SELinux, Podman, veille et réseau. Ne pas modifier la vérification
de distribution du script pour contourner ce verrou.

Ne conclure **QUALIFIÉ** qu'après des preuves datées de chaque domaine.
Ne jamais stocker de clé, jeton, conversation privée ou secret dans le dossier
de preuves.
