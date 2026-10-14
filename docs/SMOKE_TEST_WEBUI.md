# Test de fumée Open WebUI — Fedora 45 Workstation + GNOME 51

Ce test valide ce que la CI ne peut pas prouver : l'image Open WebUI réellement exécutée, le
navigateur, le micro, la B580, le stockage des uploads et le vrai fournisseur cloud. Il se fait
**après** une CI verte. Un échec n'est jamais contourné en désactivant SELinux, le filtre, le
budget ou les confirmations.

## 0. Vérifier que l'explication est compréhensible

Avant les essais techniques, ouvrir le [README](../README.md), le [guide](GUIDE.md),
les [rôles et outils](fiches/07-roles-et-outils.md), l'[architecture](fiches/11-comment-ca-marche.md)
et le [parcours DevOps](EXEMPLE_PARCOURS_DEVOPS.md) sur GitHub ou en rendu Markdown.

- Vérifier que les deux SVG s'affichent, restent lisibles et que les flèches se comprennent.
- Identifier où se trouvent Open WebUI, le worker, OpenClaw, Qwen, les fichiers et la route cloud.
- Retrouver **chaque rôle** et **un outil réservé** sans lire le code source.
- Vérifier que « lint », « test », « livraison » et « déploiement réel » ne sont pas confondus.
- Vérifier qu'aucune légende ne présente une fonctionnalité non testée comme validée sur Fedora.

Ce contrôle est **humain et visuel** : un test XML ou une CI verte ne garantit pas
la bonne lisibilité du diagramme.

## 1. Préparer et contrôler les services

```bash
./menu.sh --action install --apply
./menu.sh --action context-probe --apply
./menu.sh --action webui-install --apply
./menu.sh --action health
./menu.sh --action webui-status
```

Attendu :

- Fedora 45 Workstation + GNOME 51 sur Wayland, SELinux `Enforcing`, firewalld actif ;
- Qwen entièrement ou majoritairement sur la B580 selon le résultat de `context-probe` ;
- services OpenClaw, pont, dashboard, Open WebUI et `clawfedora-speech` actifs ;
- ports 3000, 18789, 18890, 18891 et 18893 en boucle locale seulement ;
- aucune erreur répétée dans `journalctl --user`.

Créer le compte administrateur unique dans Open WebUI, puis fermer les inscriptions :

```bash
./menu.sh --action webui-seal --apply
```

Redémarrer Open WebUI et confirmer qu'un second compte ne peut pas être créé.

## 1 bis. Boutons de l'interface

Après `webui-seal --apply`, dans le navigateur :
- vérifier que les filtres et actions `clawfedora_files` et
  `clawfedora_project_actions` sont présents, actifs et globaux ;
- vérifier que **Voir les projets**, **État du projet**, **Voir les sources**,
  **Commandes disponibles**, **Quel modèle choisir ?** et
  **Budget DeepSeek** apparaissent sous les messages ;
- cliquer sur chacun, vérifier le retour en notification et l'absence
  d'appels au modèle, de dépense cloud ou de transition de projet ;
- sélectionner un projet de test puis **Voir les sources** : vérifier les noms
  des fichiers importés et leur état, sans afficher leur contenu ni modifier
  l'index ; tester l'absence de projet et l'inventaire modifié ;
- les six boutons **en lecture seule** doivent continuer à fonctionner sans
  confirmation ni transition de projet ;
- sélectionner un projet fictif de test, puis vérifier la présence des huit
  actions **Analyser**, **Plan**, **Lancer**, **Pause**, **Reprendre**,
  **Auditer**, **Relire**, **Préparer la livraison** ;
- **annuler** chaque confirmation : aucune commande ni transition ne doit suivre ;
- déconnecter le navigateur pendant un dialogue : aucun déclenchement ;
- vérifier que `WEBSOCKET_EVENT_CALLER_TIMEOUT=300` est conservé
  dans l'environnement généré du conteneur, puis laisser une confirmation
  ouverte jusqu'au délai : la Function doit échouer **sans action** ;
  un retour `{"error": "..."}` du navigateur ne vaut jamais accord ;
- confirmer une action dans un état incompatible : le pont doit la refuser ;
- confirmer une action dans un état compatible : le changement doit passer
  par les contrats et le verrou du moteur existant ;
- vérifier que « Préparer la livraison » requiert encore une phrase d'approbation
  **distincte**, à usage unique, et n'effectue pas la livraison par son clic ;
- vérifier que le compte non-administrateur ne voit ou n'utilise aucune action
  de pilotage et qu'aucun historique confidentiel n'est transmis par les boutons ;
- utiliser le bouton **Créer un projet** avec titre et demande de test, puis
  vérifier que la simple confirmation du navigateur n'a créé aucun projet :
  une phrase `approuver creation CODE` doit être envoyée séparément ;
- annuler chacun des deux champs et la confirmation de création, tester un
  titre multiligne et une description démesurée : aucun projet créé, aucun
  appel au modèle, aucune fuite d'historique ni d'identifiants ;
- sélectionner un projet, répondre à une question de cadrage via
  **Répondre à une précision**, puis vérifier que l'annulation, une
  erreur de navigateur et un numéro invalide n'envoient rien ;
- sélectionner une tâche déjà planifiée, demander une révision via
  **Demander une révision**, puis vérifier que le navigateur affiche le
  numéro de tâche et le motif à saisir ; annuler chacun des champs ou
  la confirmation et vérifier qu'aucune révision n'est créée ;
- confirmer le dialogue de révision : vérifier que le pont énumère
  les tâches affectées et demande une phrase indépendante
  `approuver revision CODE` ; avant de saisir cette phrase, **aucun**
  état ou livrable ne doit changer ; tester un code expiré puis un
  code valide sur un projet de test ;
- vérifier que l'Action installée se nomme « ClawFedora — contrôle des projets »
  et que sa description ne prétend plus limiter les boutons à la lecture seule ;
- comparer `!budget` et le bouton Budget DeepSeek : mêmes montants du
  journal local, aucune génération IA ni appel OpenRouter ;
- saisir un relevé fournisseur factice uniquement dans un laboratoire de test
  séparé, vérifier que l'estimation ne devient **jamais** une facture annoncée.

## 1 ter. Streaming incrémental — raccordement opt-in

Le code du pont prévoit désormais une source de fragments SSE **injectée par le
serveur**, limitée au Mentor **Qwen local** sans projet ni pièce jointe.
Dans l'installation normale, cette source n'est **pas activée** :
le chemin CLI validé continue de renvoyer la réponse complète.

Les tests de CI prouvent que, lorsqu'une source de test autorisée est
injectée, Open WebUI peut recevoir un fragment **avant** la fin de la
génération, que le worker reste verrouillé et qu'un échec en cours de
flux n'est jamais présenté comme une réponse complète.

**Le raccordement canary est disponible dans le code, mais désactivé par défaut.**
Le pont peut désormais sélectionner le streaming natif après activation explicite,
prévalidation CLI exacte (versions/modèle Qwen/roster/outils) et contrôle du jeton
opérateur 0600. L'API privilégiée reste inaccessible à Open WebUI : seul le pont
local peut l'appeler. L'activation et le retour arrière sont documentés dans
[Streaming SSE natif](STREAMING_SSE_PREPARATION.md).

**Test final sur Fedora** : vérifier les fragments en direct, l'annulation,
la fermeture du générateur, le verrou, la sécurité des commandes et l'absence
de coût cloud. Sans marqueur, vérifier que le CLI reste sélectionné. Une CI
verte seule ne valide ni OpenClaw réel ni le navigateur.

## 2. Conversation locale

Dans `http://127.0.0.1:3000` :

1. choisir « Mentor infrastructure/OPS · local » ;
2. demander une explication simple sur systemd ;
3. vérifier que la réponse porte le rôle attendu et qu'aucun modèle cloud n'est utilisé ;
4. lancer `./menu.sh --action cloud-status` : aucun coût ne doit apparaître.

Tester une conversation assez longue : l'interface doit rester utilisable et le bandeau
« contexte allégé » doit apparaître avant qu'une requête trop grande ne soit refusée.

## 2 bis. Petits fichiers en chat local, sans projet

Dans une nouvelle conversation sans projet :

1. Sélectionner « Mentor infrastructure/OPS · local », joindre un petit `main.tf` UTF-8
   et demander une explication. La réponse doit expliquer son contenu sans créer de projet.
2. Joindre un `README.md` et un `deployment.yaml` (moins de 12 000 octets cumulés).
3. Tenter un cinquième fichier et un fichier de plus de 12 000 octets :
   refus explicite, aucune inférence.
4. Joindre un petit PDF texte et un DOCX : vérifier que seules les portions
   textuelles bornées sont transmises au Mentor local, sans créer de projet.
   Pour un PPTX ou XLSX, contrôler que le résultat indique une extraction
   partielle, sans garantir mise en page ni formules.
5. **Vision désactivée par défaut :** joindre une petite image PNG/JPEG
   et vérifier que seules les métadonnées sont décrites. Un PDF scanné
   doit être refusé sans activation. **Canary de vision explicitement activé :**
   lancer d'abord `clawfedora-vision-smoke --root "$PWD"
   --runtime-root /srv/openclaw-local --apply` sur une image et un
   PDF synthétiques, puis joindre une vraie image publique sans données
   privées. Vérifier les objets/couleurs décrits et l'absence de repli
   cloud. Le simple retour d'une réponse ne prouve pas la précision.
   Refuser un exécutable, fichier corrompu, archive ZIP, PDF trop long
   ou empreinte invalide avant inférence.
6. Choisir « · cloud (DeepSeek) » et joindre le même `main.tf` :
   **refus**, aucun appel OpenRouter et aucun coût enregistré.
7. Vérifier que le fichier n'a créé aucun dossier sous `projects/`.
   Il peut rester dans le stockage normal d'Open WebUI : vérifier aussi sa suppression.

Ces vérifications ne remplacent pas les tests de l'ingestion complète dans un projet.

## 3. Commandes projet de bout en bout

Dans une nouvelle conversation :

1. écrire une demande de petit projet ;
2. `!creer smoke-webui`, relire puis taper la phrase de confirmation seule ;
3. `!projet smoke-webui` ;
4. joindre un petit `README.md` et un fichier YAML **avant** l'analyse ;
5. `!analyser`, puis approuver ;
6. répondre aux éventuelles précisions avec `!questions` et `!repondre` ;
7. `!planifier`, puis approuver avec `!valider` ;
8. `!lancer`, suivre avec `!etat` ;
9. si le mode guidé crée une pratique : `!pratique <tâche>`, joindre exactement les fichiers
   attendus puis `!soumettre <tâche> <explication>` ;
10. quand l'état le permet : `!auditer`, puis `!relire` ;
11. demander une modification avec `!modifier <tâche> <raison>` et vérifier que rien ne change
    avant la phrase de confirmation ;
12. atteindre de nouveau `PACKAGING`, puis `!livrer` et confirmer.

Attendu : les mêmes états et livrables apparaissent dans l'Atelier Projets. Aucune commande du
modèle lui-même ne doit changer l'état.

## 4. Pièces jointes

Vérifier séparément :

- texte / Markdown / YAML : indexés par la chaîne canonique ;
- DOCX/PPTX/XLSX : extraction locale ;
- ZIP normal : extraction sûre ;
- PDF : statut `TOOL_REQUIRED` jusqu'à sa lecture par l'outil PDF ;
- image : lecture locale ; aucune image ne doit partir sur la route cloud ;
- archive `../escape`, lien symbolique, fichier secret évident : refus ;
- ajout d'un fichier après le début de l'analyse : refus explicite.

### Plan B du fichier original

Si l'upload via Open WebUI ne transmet pas correctement le fichier original avec la version
épinglée :

```bash
mkdir -p /srv/openclaw-local/state/chat-import/inbox/smoke-webui
cp /chemin/vers/source.pdf /srv/openclaw-local/state/chat-import/inbox/smoke-webui/
```

Puis dans le chat :

```text
!importer
```

Le dossier doit être consommé seulement après une copie/ingestion réussie.

## 5. Voix locale

Dans Open WebUI :

1. dicter une phrase française ;
2. **relire le texte transcrit avant de l'envoyer** ;
3. vérifier qu'une phrase technique (systemd, Terraform, Ansible) reste intelligible ;
4. lire une réponse à voix haute ;
5. vérifier que le mode appel/mains libres n'est pas proposé comme mode automatique.

Mesurer :

```text
première transcription : ____ s
transcription suivante  : ____ s
RAM du service speech   : ____ MiB
CPU pendant STT         : ____ %
```

Le service vocal doit rester sur `127.0.0.1:18893`. La B580 reste réservée à Qwen : Whisper
est configuré CPU/int8.

## 5 bis. Profils DeepSeek (à qualifier après stabilisation)

Avant un vrai appel OpenRouter, tester les trois profils sans désactiver les
garde-fous : `./menu.sh --action cloud-profile` affiche `approfondi`
si aucun profil n'a été enregistré. `cloud-set-profile --value equilibre`
sans `--apply` n'écrit **rien** ; avec `--apply`, le profil devient
`equilibre` et apparaît dans `cloud-status` et `!budget`.

Vérifier aussi qu'un changement est refusé pendant une tâche du worker
et que le fichier privé `state/cloud/reasoning-profile.json` reste en 0600.
Une valeur non prévue ou un lien symbolique doit bloquer l'appel cloud
avant réservation et envoi. Ne jamais corriger cela en supprimant le filtre.

Pour `rapide`, `equilibre` et `approfondi`, effectuer **la même
question publique de référence** en notant le provider effectif, la latence,
la qualité humaine, les tokens et la dépense réelle sur OpenRouter. Le test
doit vérifier que `require_parameters: true` n'a pas été assoupli et
qu'un hébergeur incompatible **échoue** au lieu d'ignorer l'effort demandé.
Revenir à `approfondi` après comparaison si nécessaire.

## 6. DeepSeek V4.1 Flash réel

Seulement avec une clé OpenRouter limitée et des crédits prépayés :

```bash
./menu.sh --action cloud-set-key
./menu.sh --action cloud-enable --value 12
./menu.sh --action cloud-enable --value 12 --apply
./menu.sh --action cloud-status
```

Dans le chat, choisir « · cloud (DeepSeek) » et poser une question **publique** complexe.

Vérifier :

- provenance cloud visible ;
- modèle réellement servi = `deepseek/deepseek-v4.1-flash` ;
- contexte cloud déclaré à 1 048 576 tokens, sortie 32 768 ;
- la passerelle impose `reasoning.effort=xhigh` ;
- routage `throughput` sous `provider.max_price` ;
- coût visible dans le journal et cohérent avec OpenRouter ;
- un faux jeton GitHub dans le message déclenche le passage local visible ;
- un projet sans accord cloud n'envoie aucune de ses sources ;
- une image de projet reste locale même avec l'accord cloud.

Si OpenRouter répond « no endpoints », ne pas relâcher `data_collection: deny` ou le plafond de
prix sans nouvelle décision explicite.

## 7. Repli, redémarrage et sauvegarde

```bash
./menu.sh --action backup
systemctl --user restart clawfedora-webui.service
systemctl --user restart clawfedora-webui-bridge.service
systemctl --user restart clawfedora-speech.service
./menu.sh --action health
```

Vérifier que :

- projets et conversations restent présents ;
- les secrets cloud ne sont pas dans la sauvegarde ;
- la clé OpenRouter doit être ressaisie après restauration ;
- le service vocal redémarre sans retélécharger son modèle ;
- `cloud-disable --apply` rend l'ensemble utilisable entièrement en local.

## 8. Critère de fin

Le lot Open WebUI est validé sur la machine seulement si tous les cas ci-dessus passent sans
désactiver un garde-fou. Reporter les mesures et anomalies dans `STATUS.md` avant de déclarer
l'installation Fedora « vérifiée ».
