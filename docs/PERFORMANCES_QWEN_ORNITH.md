# Tableau de performances Qwen / Ornith — mesures réelles uniquement

## Principe

L'Atelier expose une page `/performance.html` et un endpoint en **lecture
seule** `GET /api/performance`. Ces deux éléments n'exécutent **aucun**
benchmark, ne contactent pas Ollama, ne téléchargent aucun modèle et
n'appliquent aucun réglage GPU.

La page affiche uniquement le **dernier relevé de benchmark effectué
explicitement par l'opérateur** via `clawfedora-gpu-benchmark`. Sans relevé,
elle indique « Aucune mesure enregistrée », sans inventer de débit ni
présumer que la configuration Fedora 45/B580 est qualifiée.

## Effectuer une mesure sur le PC Fedora

Depuis la racine du dépôt, avec l'environnement de l'Atelier correctement
installé, définir le chemin **réel** du runtime local géré, puis lancer :

```bash
# Adapter au chemin utilisé lors de l'installation locale.
RUNTIME_ROOT="/data/IA/Openclaw"

# Sans --apply : aucune inférence, aucune écriture.
clawfedora-gpu-benchmark --root "$PWD" --models all

# Mesure volontaire et enregistrement privé des résultats.
clawfedora-gpu-benchmark --root "$PWD" --models all \
  --apply --record --runtime-root "$RUNTIME_ROOT"
```

La mesure parcourt **Qwen 3.5 9B puis Ornith 1.5 9B**, avec 8K, 16K,
32K de contexte pour chacun. L'option facultative `--near-limit` porte
le remplissage ciblé de 60 % à 90 % : elle sollicite davantage la VRAM et
ne doit être lancée qu'après la qualification de base.

L'option `--record` est **refusée** sans `--apply` et `--runtime-root`.
Toute mesure active exige le runtime géré et son volume de données valide,
même sans enregistrement. Le chemin par défaut vient du contrat de stockage.
Le verrou exclusif existant de l'Atelier est conservé
pendant toute la mesure et empêche l'exécution simultanée d'un worker
ou d'une session de mesure dans le même runtime. Le mode jeu est refusé.
Aucun paramètre Ollama, `num_ctx` de production, Flash Attention,
cache KV, modèle ou profil cloud n'est modifié.

## Rapport persistant

Le résultat est enregistré sous
`$RUNTIME_ROOT/state/performance/gpu-benchmark.json` :
répertoire privé 0700 et fichier 0600, écriture atomique.

Le fichier ne contient que les noms d'alias autorisés, les tailles
de contexte, verdicts, VRAM résidente du **modèle** (pas la VRAM globale),
taux de résidence GPU, temps de chargement, tokens/s de lecture du prompt
et de génération, remplissage et date UTC. Il n'enregistre
**ni prompt, ni réponse, ni conversation, ni secret, ni jeton**.

Une mesure ultérieure remplace le précédent rapport. Si seul Qwen
ou seul Ornith a été mesuré, l'autre modèle est indiqué **non mesuré** :
les valeurs de deux journées ou profils différents ne sont jamais
fusionnées artificiellement dans une même comparaison.

Le chargement du rapport vérifie le format, la provenance déclarée,
les plages numériques, l'identité des modèles, l'absence de lien
symbolique et les permissions. Un rapport corrompu, aux valeurs incohérentes
ou accessible à d'autres utilisateurs n'affiche **aucune métrique**.
Ce contrôle de format et de permissions ne constitue toutefois pas une
attestation cryptographique des mesures.
Un rapport de plus de 30 jours est marqué **ancien**.

## Lire les résultats correctement

- `FULL_GPU` mesure le placement résident du modèle pendant **ce test**,
  et **n'est pas** une certification des sept agents ou d'un projet.
- Le plus grand contexte `FULL_GPU` est **provisoire** tant qu'un
  essai près de la limite n'a pas été réalisé et contrôlé.
- Une mesure à fort remplissage `near_limit_qualified` vérifie les
  seuils techniques enregistrés, pas la qualité des décisions du modèle.
- Une petite différence de tokens/s n'établit aucun gain réel :
  comparer même version Ollama, même pilote Mesa/Vulkan, même modèle,
  mêmes paramètres et même scénario, en répétant les essais.
- Le tableau ne mesure pas l'usage GPU total de Fedora/KVM, les
  sollicitations du bureau GNOME ni les performances de l'atelier
  complet. Des tests fonctionnels et une réception humaine restent requis.

## Réception avant de considérer ce chantier terminé

1. CI (Ruff, Mypy, pytest, CodeQL, Fedora contracts) sur la PR.
2. Sur Fedora, vérifier le verrou en lançant une mesure avec un autre
   worker actif : elle doit être refusée.
3. Mesurer les deux modèles, recharger `/performance.html` et vérifier
   que toutes les valeurs proviennent du rapport local exact.
4. Simuler rapport absent, ancien, 0644 et lié : l'interface ne doit
   jamais afficher de nombres fictifs ou non vérifiés.
5. Mesurer la variation du temps de réponse de Qwen/Ornith hors CI
   avant de décider d'un réglage GPU différent.

**Aucune réception GPU réelle sur Intel Arc B580 n'est prétendue dans ce lot.**
