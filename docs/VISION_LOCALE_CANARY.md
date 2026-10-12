# Canary de compréhension visuelle — Qwen local seulement

Cette fonction est **désactivée par défaut**. Sans activation, le chat libre
continue d'afficher les métadonnées d'images et de refuser les PDF scannés
sans texte. Aucun changement de modèle, de coût cloud ou de service n'est
effectué par le code du dépôt tant que l'opérateur ne crée pas le marqueur.

## Garanties avant inférence

- Chat **local**, sans projet et sans route DeepSeek ; l'authentification et
  les chemins de fichiers restent ceux du pont Open WebUI.
- Même prévalidation que le runner normal : version OpenClaw/Ollama, digest
  du Qwen `qwen3.5:9b-q4_K_M`, roster des sept agents et outils refusés.
- Appel **uniquement** à `127.0.0.1:11434` avec l'API Ollama native,
  proxy et redirections refusés ; aucun modèle librement fourni par le chat.
- Le Qwen local doit annoncer `vision` via `/api/show`. Le nom retourné
  par `/api/chat` doit être identique au nom du catalogue, la réponse
  doit être complète et bornée, sous le verrou unique du worker.
- Image PNG/JPEG/WebP vérifiée et limitée à 2 Mio/12 millions de pixels.
  PDF scanné limité à **2 pages**, rendu en images de 1024 pixels de côté
  maximum par Poppler local dans un dossier temporaire privé.
- **Aucun fallback OpenRouter** : une erreur donne un refus explicite.
  Les descriptions sont une observation probable du modèle, jamais une
  transcription OCR certifiée ni une preuve de contenu.

## Activation manuelle et réversible

Depuis la session du propriétaire du runtime, et uniquement après avoir
vérifié que le modèle installé supporte réellement les images :

```bash
RUNTIME_ROOT="/chemin/vers/le/runtime-gere"
install -m 0600 /dev/null "$RUNTIME_ROOT/state/webui/local-vision.enabled"
printf 'qwen-local-vision-v1\n' \
  > "$RUNTIME_ROOT/state/webui/local-vision.enabled"
chmod 0600 "$RUNTIME_ROOT/state/webui/local-vision.enabled"
systemctl --user restart clawfedora-webui-bridge.service
```

Dans **une conversation locale sans projet**, joindre une image publique
ou un PDF scanné synthétique et demander une description. Vérifier le nom
du Qwen, la réponse de la bonne image, l'absence de requête cloud et le
verrou. Comparer sur un jeu de références visuelles à correction humaine
avant de déclarer le résultat fiable.

## Retour arrière

```bash
rm -- "$RUNTIME_ROOT/state/webui/local-vision.enabled"
systemctl --user restart clawfedora-webui-bridge.service
```

Les images redeviennent **métadonnées uniquement** ; les PDF scannés sont
à nouveau refusés sans OCR. Aucun modèle n'est supprimé, aucune clé ou
permission cloud n'est modifiée.

## Limites de validation

La CI couvre la logique de refus, de sélection exacte du modèle, de verrou et
de non-fallback avec une interface Ollama simulée. **Elle ne prouve pas**
la qualité visuelle réelle du Qwen sur la B580 ni l'intégration navigateur.
Une vérification réelle sur Fedora et un test avec des images de référence
restent obligatoires avant activation durable.
