# Test de fumée Open WebUI — Fedora 44

Ce test valide ce que la CI ne peut pas prouver : l'image Open WebUI réellement exécutée, le
navigateur, le micro, la B580, le stockage des uploads et le vrai fournisseur cloud. Il se fait
**après** une CI verte. Un échec n'est jamais contourné en désactivant SELinux, le filtre, le
budget ou les confirmations.

## 1. Préparer et contrôler les services

```bash
./menu.sh --action install --apply
./menu.sh --action context-probe --apply
./menu.sh --action webui-install --apply
./menu.sh --action health
./menu.sh --action webui-status
```

Attendu :

- Fedora 44, SELinux `Enforcing`, firewalld actif ;
- Qwen entièrement ou majoritairement sur la B580 selon le résultat de `context-probe` ;
- services OpenClaw, pont, dashboard, Open WebUI et `clawfedora-speech` actifs ;
- ports 3000, 18789, 18890, 18891 et 18893 en boucle locale seulement ;
- aucune erreur répétée dans `journalctl --user`.

Créer le compte administrateur unique dans Open WebUI, puis fermer les inscriptions :

```bash
./menu.sh --action webui-seal --apply
```

Redémarrer Open WebUI et confirmer qu'un second compte ne peut pas être créé.

## 2. Conversation locale

Dans `http://127.0.0.1:3000` :

1. choisir « Mentor infrastructure/OPS · local » ;
2. demander une explication simple sur systemd ;
3. vérifier que la réponse porte le rôle attendu et qu'aucun modèle cloud n'est utilisé ;
4. lancer `./menu.sh --action cloud-status` : aucun coût ne doit apparaître.

Tester une conversation assez longue : l'interface doit rester utilisable et le bandeau
« contexte allégé » doit apparaître avant qu'une requête trop grande ne soit refusée.

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
