# Premier essai sur la machine

La CI prouve que le logiciel est cohérent et que le prompt réel d’OpenClaw tient dans le contexte. Elle ne peut pas prouver ce qui dépend du PC : que la B580 est utilisée, que 32K tiennent dans ses 12 Gio et que la vitesse est confortable. Ce guide produit ces trois réponses en moins d’une heure, avant tout le reste (gates L4 à L8, comparaisons de modèles), qui est facultatif.

## 1. Installer

```bash
./menu.sh --action validate
./menu.sh --action install            # aperçu, ne modifie rien
./menu.sh --action install --apply
```

Se déconnecter puis se reconnecter une fois : les groupes `render` et `video` ne s’appliquent qu’à une nouvelle session.

## 2. Vérifier que le GPU travaille

```bash
./menu.sh --action hardware-l3
./menu.sh --action health
journalctl -u ollama -b | grep -i -E "vulkan|B580|vram"
```

Attendu : la B580 est listée comme périphérique Vulkan dans le journal d’Ollama. Si seul le processeur apparaît, s’arrêter ici et suivre [TROUBLESHOOTING.md](TROUBLESHOOTING.md) : rien de ce qui suit n’a de sens sans GPU.

## 3. Mesurer le contexte 32K

```bash
./menu.sh --action context-probe --apply
```

La commande remplit environ 60 % du contexte, génère une courte réponse et affiche un rapport. Trois lignes comptent :

| Ligne | Lecture |
|---|---|
| `verdict` | `FULL_GPU` : tout tient sur la carte. `PARTIAL_CPU_OFFLOAD` : une partie passe sur le processeur. |
| `output_tokens_per_second` | Vitesse d’écriture de la réponse. En dessous d’environ 10, le chat devient pénible. |
| `prompt_tokens_per_second` | Vitesse de lecture du contexte. Elle fixe l’attente avant le premier mot sur un long historique. |

Si le verdict n’est pas `FULL_GPU`, ou si la vitesse ne convient pas, comparer avec 16K :

```bash
clawfedora-ops --runtime-root /srv/openclaw-local context-probe --context 16384 --apply
```

Puis appliquer la valeur retenue comme expliqué dans [DAILY_PROFILE.md](DAILY_PROFILE.md#pourquoi-32k-et-comment-le-vérifier). Noter les chiffres obtenus dans [`../STATUS.md`](../STATUS.md) : ce sont les premières mesures réelles du projet.

## 4. Poser une vraie question

```bash
./menu.sh --action webui-install --apply
```

Ouvrir `http://127.0.0.1:3000`, créer le compte, puis fermer les inscriptions avec `./menu.sh --action webui-seal --apply`. Poser au mentor une question de son niveau réel, par exemple un blocage rencontré cette semaine, et poursuivre sur cinq ou six échanges.

À observer : la réponse est-elle juste, utile, en français naturel ? Le temps d’attente est-il acceptable ? La réponse arrive d’un bloc, sans affichage progressif : c’est une limite connue de cette version.

## 5. Décider de la suite

- Réponses utiles et vitesse correcte : l’atelier est utilisable au quotidien. Le reste de la documentation devient une référence, pas un prérequis.
- Réponses trop faibles pour le besoin : c’est la limite d’un modèle 9B, pas un défaut d’installation. Voir [MODEL_SELECTION_2026_10.md](MODEL_SELECTION_2026_10.md) pour comparer Gemma et Granite sur ses propres questions.
- Problème matériel ou d’installation : [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
