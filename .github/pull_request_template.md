## Ce que change cette modification

Le problème réel et le résultat attendu, en quelques lignes.

## Vérifications

- [ ] `make ci` passe
- [ ] si les fichiers `agents/`, les outils ou les limites ont changé : `make native-schema` et `make native-prompt` passent
- [ ] la fiche concernée dans `docs/fiches/` est à jour
- [ ] si le cloud est touché (`cloud_*`, `config/core/cloud_policy.yaml`, passerelle, filtre, budget) : `make native-cloud` passe, rien n'envoie de contenu sans passer par le filtre, et aucun secret n'est écrit dans Git, un journal ou une sauvegarde
- [ ] rien n'ouvre un port réseau, ne désactive SELinux ou le pare-feu, ni ne donne au modèle un outil d'exécution
