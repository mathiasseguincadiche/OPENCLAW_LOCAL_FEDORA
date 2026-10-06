# Comparer l’accompagnement du vrai Qwen

Le style décrit par une charte ne prouve pas son efficacité. La suite `benchmarks/suites/mentor_ops_fr.yaml` contient douze situations en français couvrant les sept rôles : Terraform, Ansible, diagnostic Docker/Kubernetes, artefacts CI, identité cloud, restauration, rapport non fiable, retrait d’aide, rédaction, sources et réponse courte en incident.

Le module `clawfedora.pedagogy_eval` capture les réponses du client natif déjà utilisé par le chat. Il conserve les identités du Qwen adopté, les versions verrouillées, les hashes des fichiers réellement déployés et les conditions du mentor. Les prompts et historiques sont fixés. Une session neuve par cas; même verrou que chat/projets, aucun projet ni note modifié, aucun changement de routage. La collecte est volontaire, séquentielle et utilise les budgets quotidiens. Elle peut prendre plusieurs minutes par cas; commencer par une petite sélection.

## Avant et après une migration

Depuis le dépôt à jour, avec le compte Fedora habituel, `make install` prépare la venv de travail `.venv` sans migrer les services ni les workspaces. La commande agit sur les workspaces **déployés**, pas sur les seuls fichiers du checkout. Cette venv séparée permet de capturer les anciens profils encore installés, avant de les migrer; conserver le runtime natif inchangé pour cette première capture.

```bash
mkdir -p ~/comparaisons-ops
.venv/bin/python -m clawfedora.pedagogy_eval capture \
  --runtime-root ~/.local/share/openclaw-local \
  --output ~/comparaisons-ops/avant \
  --case ansible-idempotence --case ansible-fading --case urgent-service
```

Adapter `--runtime-root` au répertoire réel; le supprimer utilise la résolution habituelle du projet, dont `OPENCLAW_LOCAL_FEDORA_ROOT`. Les sorties sont nouvelles : aucun dossier de capture existant n’est écrasé. Le dossier parent doit exister. Une erreur après le début de la collecte laisse un manifest `INCOMPLETE`, jamais un verdict de réussite pédagogique.

Actualiser ensuite l’installation selon [UPGRADE.md](UPGRADE.md), puis relancer exactement les mêmes cas vers un nouveau dossier `apres`. Conserver modèle/digest, versions OpenClaw/Ollama, notes du mentor et contexte du projet relié identiques. Ne pas réutiliser les conversations de la première capture. Sans `--case`, les douze cas sont capturés.

```bash
.venv/bin/python -m clawfedora.pedagogy_eval compare \
  --before ~/comparaisons-ops/avant \
  --after ~/comparaisons-ops/apres \
  --output ~/comparaisons-ops/relecture
```

Ouvrir `comparaison.html` dans le navigateur. Chaque cas présente la question, l’historique fixé, les critères et deux réponses A/B dont l’ordre est tiré au sort. Le texte est échappé, sans script ou ressource distante. Garder `correspondance.json` fermé jusqu’à la relecture pour masquer les étiquettes avant/après. `provenance.json` garde les conditions et aucun score automatique.

Le comparateur refuse captures incomplètes/modifiées, cas ou suite différents, modèle/versions/contexte différents, mélange simulation/natif et profils déployés identiques. Si les anciens profils ont déjà été remplacés sans capture, ne pas présenter deux exécutions des nouveaux profils comme un avant/après. Une première série peut alors servir de référence pour la prochaine révision pédagogique; ne pas réinstaller arbitrairement un ancien runtime sur le poste.

## Ce que l’humain vérifie

Pour chaque paire, noter la préférence A/B/équivalentes et son motif :

- **Exactitude** : mécanisme correct, source pertinente, limites et incertitudes conservées. Une erreur technique prime sur une belle formulation.
- **Clarté** : vocabulaire défini, exemple compréhensible, quantité de détails utile.
- **Adaptation** : acquis Linux/réseau réutilisés, aide adaptée aux essais, réponse courte respectée.
- **Action** : prochaine étape réalisable, effet prévu, observation et diagnostic; retour arrière si pertinent.
- **Autonomie** : aide suffisante pour commencer, sans fournir tout l’exercice ou certifier une compétence.

Relire une notion délicate avec ses sources officielles. L’auditeur utilise le même Qwen : il ne remplace pas un jugement indépendant. Si la préférence n’est pas claire, reprendre un petit sous-ensemble dans de nouvelles sessions; une paire unique ne démontre pas un gain stable. Les durées capturées sont informatives, pas un benchmark GPU ni un score d’apprentissage.

Le compte rendu utile garde les cas, erreurs, préférences, limites et prochains ajustements. Les captures restent locales; aucun modèle supplémentaire, finetuning, service permanent, quiz automatique ou agenda n’est installé. Les tests du dépôt exercent le collecteur avec réponses **simulées** et les rapports le signalent explicitement. Ils ne prouvent pas la qualité du Qwen sur Fedora/B580.
