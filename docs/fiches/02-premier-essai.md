# Premier essai

[← Guide](../GUIDE.md)

Les tests automatiques du dépôt vérifient que le logiciel est cohérent. Ils ne peuvent pas vérifier ce qui dépend de ton PC : que la B580 est bien utilisée, que le contexte tient dans ses 12 Go et que la vitesse est confortable. Cette fiche produit ces trois réponses.

## 1. Les services tournent-ils ?

```bash
./menu.sh --action health
```

Chaque ligne commence par `PASS` ou `FAIL`. Un `FAIL` indique le composant en cause : va à [Dépanner](10-depanner.md).

## 2. La carte graphique est-elle utilisée ?

```bash
./menu.sh --action check-gpu
journalctl -u ollama -b | grep -i -E "vulkan|B580|vram"
```

Attendu : la B580 apparaît comme périphérique Vulkan dans le journal d'Ollama. Si seul le processeur apparaît, arrête-toi ici : sans carte graphique, les réponses seraient trop lentes pour être utilisables.

## 3. Le contexte tient-il sur la carte, et à quelle vitesse ?

```bash
./menu.sh --action context-probe --apply
```

La commande remplit environ 60 % du contexte, génère une courte réponse et affiche un rapport. Trois lignes comptent :

| Ligne | Lecture |
|---|---|
| `verdict` | `FULL_GPU` : tout tient sur la carte. `PARTIAL_CPU_OFFLOAD` : une partie du modèle est passée sur le processeur. `CPU_ONLY` : la carte n'est pas utilisée. |
| `output_tokens_per_second` | Vitesse d'écriture de la réponse. En dessous d'environ 10, le chat devient pénible. |
| `prompt_tokens_per_second` | Vitesse de lecture du contexte. Elle fixe l'attente avant le premier mot quand la conversation est longue. |

Si le verdict n'est pas `FULL_GPU`, ou si la vitesse ne te convient pas, compare avec un contexte deux fois plus petit :

```bash
./menu.sh --action context-probe --context 16384 --apply
```

Puis applique la valeur retenue comme expliqué dans [Réglages](08-reglages.md#changer-la-taille-du-contexte).

Note les chiffres obtenus dans [`STATUS.md`](../../STATUS.md) : ce sont les premières mesures réelles du projet.

## 4. Les réponses sont-elles utiles ?

Ouvre `http://127.0.0.1:3000` et pose au mentor une vraie question de ta semaine, puis poursuis sur cinq ou six échanges.

À observer : la réponse est-elle juste ? Est-elle utile ? Le temps d'attente est-il acceptable ? La réponse arrive d'un bloc, sans s'afficher mot à mot : c'est une limite connue de cette version.

Teste aussi la **recherche Web**, qui sert aux informations récentes (version, option, prix, sécurité). Tous les rôles, mentor compris, peuvent chercher (4 résultats, puis lire une page jusqu'à 4 000 caractères) avec le fournisseur gratuit `parallel-free`. Demande par exemple : « Quelle est la dernière version stable d'Ansible ? Cherche sur le Web et donne tes sources. » À observer : la réponse cite-t-elle une page réellement consultée, avec sa date ? Le mentor écrit-il « NON VÉRIFIÉ ACTUELLEMENT » s'il n'a pas pu l'ouvrir ? Cette recherche n'a jamais été essayée sur ta machine : si elle échoue ou renvoie toujours le même résultat, note-le dans [STATUS](../../STATUS.md), c'est un défaut à corriger. Le fournisseur gratuit peut aussi limiter le nombre de requêtes.

## 5. Décider

- Réponses utiles et vitesse correcte : l'atelier est prêt pour le quotidien.
- Réponses trop faibles pour ton besoin : c'est la limite d'un modèle de 9 milliards de paramètres, pas un défaut d'installation. Pour une question publique, le cloud facultatif peut mieux expliquer ([Le cloud, facultatif](12-cloud.md)) ; changer de modèle local est décrit dans [Réglages](08-reglages.md#changer-de-modèle).
- Problème matériel ou d'installation : [Dépanner](10-depanner.md).
