# Profils GPU expérimentaux — préparation avant installation de Fedora

## Objectif et limites

L'atelier conserve Ollama, Vulkan, un modèle résident à la fois et les deux
modèles locaux Qwen 3.5 9B / Ornith 1.5 9B. Aucun changement de modèle, de
quantification des poids, de routage des sept agents ou de permissions.

Les variantes ci-dessous sont **implémentées dans le dépôt mais non qualifiées
sur le PC cible**. La valeur systemd ne prouve pas que le backend Vulkan
prend réellement en charge la fonctionnalité. Aucune accélération annoncée.

| Action menu | Flash Attention demandé | Cache KV demandé |
| --- | --- | --- |
| `gpu-reference` | 0 | f16 |
| `gpu-flash` | 1 | f16 |
| `gpu-q8` | 1 | q8_0 |

Les trois profils conservent la politique 32 768 tokens, le keep-alive de
3 minutes, le parallélisme de 1, le maximum d'un modèle et la file de 4.
Le profil de référence est installé par défaut, sans opt-in expérimental.
La variable historique `CLAWFEDORA_KV_CACHE_TYPE=q8_0` reste une option
explicite de configuration ; ne pas l'utiliser pendant cette recette.

## Avant l'installation de Fedora

Aucune commande système n'est à exécuter sur le poste actuel.
Les tests unitaires et les contrôles CI vérifient la génération du complément
systemd, les refus de paramètres divergents, le dry-run et la provenance du
rapport. Ils ne démarrent pas la B580, ne mesurent pas sa mémoire et
n'attestent pas le redémarrage réel d'Ollama sous Fedora.

## Recette à exécuter plus tard sur le PC cible

Terminer l'installation normale et les contrôles de santé avant cette recette.
Le worker doit être inactif, le mode jeu désactivé et Ollama en marche.
Le stockage doit être celui du runtime géré.

```bash
# Consulter le profil configuré et prévisualiser les trois changements.
./menu.sh --action gpu-profile-status
./menu.sh --action gpu-reference
./menu.sh --action gpu-flash
./menu.sh --action gpu-q8
```

Chaque changement requiert `--apply`, le verrou exclusif déjà utilisé par
l'atelier et les droits sudo de l'opérateur. Il remplace atomiquement le
complément géré `openclaw-daily.conf`, sans modifier les paramètres
d'isolation ni les autres services. SELinux reste actif. Si l'installation
du complément, le redémarrage ou la lecture du profil configuré échoue,
une restauration du complément précédent est tentée. Si la restauration
échoue, conserver la sauvegarde privée indiquée par le script et intervenir
manuellement. Ne pas continuer la recette dans cet état.

Exemple de campagne standard à exécuter **après installation** :

```bash
# Utiliser le chemin exact de ton installation.
RUNTIME_ROOT="/data/IA/Openclaw"
umask 077
mkdir -p "$HOME/gpu-reception"

./menu.sh --action gpu-reference --apply
clawfedora-gpu-benchmark --root "$PWD" --models all --apply --record \
  --runtime-root "$RUNTIME_ROOT" --expected-profile reference \
  > "$HOME/gpu-reception/reference.json"

./menu.sh --action gpu-flash --apply
clawfedora-gpu-benchmark --root "$PWD" --models all --apply --record \
  --runtime-root "$RUNTIME_ROOT" --expected-profile flash \
  > "$HOME/gpu-reception/flash.json"

./menu.sh --action gpu-q8 --apply
clawfedora-gpu-benchmark --root "$PWD" --models all --apply --record \
  --runtime-root "$RUNTIME_ROOT" --expected-profile q8 \
  > "$HOME/gpu-reception/q8.json"

# Revenir à la référence à la fin de la campagne, même si un test échoue.
./menu.sh --action gpu-reference --apply
```

Exécuter étape par étape : ne jamais enchaîner après un code retour non nul.
L'option `--expected-profile` exige `--record` et vérifie la propriété
Environment de systemd avant **et après** les mesures. Une divergence
refuse l'enregistrement et préserve le précédent rapport. Elle ne modifie
pas le service et ne prouve pas l'activation effective du backend.

La page Performances affiche uniquement le dernier relevé et son profil
configuré, ou « non contrôlé » pour un ancien rapport. Les trois exports JSON
privés ci-dessus permettent la comparaison hors ligne sans écraser les mesures
précédentes. Conserver aussi la version Ollama, le pilote Vulkan et le matériel
identiques ; ne pas prendre un débit isolé pour une preuve de supériorité.

## Décision après mesures

Comparer référence / Flash Attention / Flash Attention + q8_0 pour
chaque modèle et chaque taille 8K, 16K, 32K. Examiner la résidence VRAM,
les deux débits tokens/s, le remplissage effectif, le temps de chargement,
les journaux Ollama et les tâches InfraOps représentatives. Répéter les essais
avec les mêmes conditions ; pour la recette près de la limite, utiliser
`--near-limit` sur les candidats ayant réussi les essais de base.

Le keep-alive et le contexte restent inchangés pendant cette campagne.
OpenClaw transmet lui-même le keep-alive par requête : ne pas modifier
seulement le service Ollama en espérant un effet. Les mesures à froid/à
chaud et une éventuelle migration du contrat de contexte seront une étape
séparée après la qualification du GPU.

**Aucun profil candidat ne doit devenir le profil quotidien par défaut
avant validation matérielle et fonctionnelle des deux modèles.**
