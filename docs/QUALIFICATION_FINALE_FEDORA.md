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
ni détails de matériels ; seules les commandes systemd fixes et les deux
sondes HTTP 127.0.0.1 sont consultées. Ne pas utiliser ce rapport seul comme
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

## 3. Migration Open WebUI 0.12 sans bascule de production

```bash
bash scripts/linux/14_webui_canary.sh
bash scripts/linux/14_webui_canary.sh --apply --with-db-copy
```

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

Le chat libre actuel transmet du texte extrait et des métadonnées d'images,
**pas les pixels**. La CLI OpenClaw épinglée permet de tester séparément
une vision locale **si le modèle installé l'annonce**. Contrôler d'abord
l'identité et le digest du modèle Qwen puis exécuter, sur une image publique
sans donnée sensible :

```bash
openclaw infer image describe \
  --file ./exemple-public.png \
  --model ollama/qwen3.5:9b --json
```

Ce tag est un **exemple**, pas une affirmation du nom installé.
Ne pas exécuter avant de confirmer le tag et la capacité vision avec Ollama.
Lire le fournisseur réellement utilisé et ses éventuels fallbacks dans la
réponse JSON : un repli cloud n'est pas acceptable pour cette réception.
Les PDF scannés sans texte exigent un chemin de vision/OCR à qualifier.

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
Tester les empreintes, l'absence de chemins externes/backing QCOW2 cachés,
les permissions et les données de la copie restaurée.

## 8. Qualité des artefacts

Ouvrir un vrai runbook PDF, DOCX et Draw.io : contrôler titres, tableaux,
pagination, blocs de code, accents, diagrammes multi-vues, liens, fichiers
source et manifeste SHA-256. L'inspection visuelle est obligatoire.

| Domaine | État initial |
|---|---|
| Fedora / B580 / veille / AV1 | Non qualifié sur la machine |
| Open WebUI 0.12 / copie SQLite / navigateur | Canary logiciel, essai réel manquant |
| Streaming SSE / annulation | Code intégré, essai réel manquant |
| Vision des images et PDF scannés | Pas intégrée au chat libre |
| OpenRouter / coût réel | Essai avec accord manquant |
| Archive et restauration sur copie | Essai local manquant |
| Inspection PDF / DOCX / Draw.io | Essai visuel manquant |

Ne conclure **QUALIFIÉ** qu'après des preuves datées de chaque domaine.
Ne jamais stocker de clé, jeton, conversation privée ou secret dans le dossier
de preuves.
