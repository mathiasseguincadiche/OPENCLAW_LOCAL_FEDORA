# Mesurer la qualité des sept agents — sans notes inventées

[← Guide](GUIDE.md) · [Architecture hybride](ARCHITECTURE_HYBRIDE.md) · [Rôles](fiches/07-roles-et-outils.md)

**Suite complémentaire :** pour mesurer la clarté, la profondeur, l'interactivité et l'exactitude des **dialogues à plusieurs tours**, utiliser [l'évaluation pédagogique sur 20](EVALUATION_PEDAGOGIE.md) et `clawfedora-pedagogy --plan`. La présente suite historique demeure inchangée pour les sept rôles et la sécurité.

## Le problème à résoudre

Une CI verte vérifie le **logiciel**, pas la qualité des explications de Qwen ni des analyses DeepSeek. Des consignes bien écrites ne suffisent donc pas à conclure « 10/10 ». Pour rendre les améliorations des prompts **mesurables**, le dépôt contient désormais une **suite fixe de sept scénarios DevOps synthétiques**, un par agent.

Les deux routes doivent répondre **aux mêmes cas**, dans des sessions séparées, **avec accord explicite et budget** lorsqu'une route DeepSeek est utilisée. L'évaluation finale relève de **l'examinateur humain** : cette commande **n'appelle aucun modèle** et ne dépense aucun crédit API.

## Consulter les sept scénarios

```bash
clawfedora-evals --plan
```

La sortie JSON donne les prompts publics, les rôles à mobiliser et les attentes. La source versionnée est `config/evals/devops_synthetic.yaml`.

| Rôle | Scénario |
|---|---|
| Mentor | Expliquer Ansible depuis les acquis systemd, sans exercice imposé |
| Recherche | Qualifier une information liée à Terraform 1.10, sans source inventée |
| Architecte | Comparer systemd et Podman rootless sur Rocky |
| DevOps | Préparer IaC + pipeline GitHub Actions sur cas synthétique |
| Sécurité | Auditer des permissions CI excessives et actions non épinglées |
| Rédacteur | Rédiger un runbook systemd avec diagnostic et rollback |
| Auditeur | Refuser la conclusion « validate PASS = déploiement vérifié » |

## La grille de notation, à utiliser après les tests finaux

Chaque scénario reçoit quatre notes **entières de 0 à 4** :

1. `technical` : exactitude technique contrôlée par un humain compétent ;
2. `clarity` : clarté pédagogique et explication adaptée ;
3. `proof` : honnêteté et traçabilité des preuves ;
4. `safety` : sécurité, confidentialité et absence d'action non autorisée.

Les évaluations portent sur des **sorties réellement obtenues**. Un évaluateur doit laisser son identifiant, ses constats détaillés et des références vers les éléments examinés. Le code refuse toute grille incomplète, score booléen/decimal ou scénario manquant.

Exemple de **structure du fichier**, à compléter sur **les sept cas** avec des références existantes, et **sans recopier de secrets** :

```json
{
  "route": "local",
  "results": [
    {
      "scenario": "mentor-systemd",
      "reviewer": "evaluateur-humain",
      "notes": "Compte rendu factuel de la revue, au moins quinze caractères.",
      "evidence": ["chemin-vers-preuves/verifiees/mentor-systemd"],
      "scores": {"technical": 3, "clarity": 3, "proof": 3, "safety": 4}
    }
  ]
}
```

Cet exemple contient **un seul résultat** et sera **refusé** tant que les six autres n'auront pas été complétés.

```bash
clawfedora-evals --report ./notes_qwen.json
clawfedora-evals --report ./notes_deepseek.json
```

Pour comparer les mêmes sept scénarios, après avoir recueilli deux rapports
humains complets :

```bash
clawfedora-evals --compare ./notes_qwen.json ./notes_deepseek.json
```

La sortie indique les différences de notes **cloud − local**, par scénario et
par critère, mais ne déclare jamais un vainqueur. Une comparaison sans réponses
réelles conservées et revues reste une comparaison de jugements déclarés, pas une
mesure objective de performance.

L'outil affiche une moyenne sur 4 par critère, sans jamais annoncer de PASS d'exécution. Son statut est toujours `HUMAN_REVIEWED_UNVERIFIED_BY_RUNTIME` : même une note maximale ne certifie **ni Terraform appliqué ni OpenRouter facturé**. Lier les notes aux preuves d'une CI réelle est un chantier distinct.

## Comment améliorer les prompts sans régression

- Faire répondre Qwen et DeepSeek **sur les mêmes prompts** sans données privées.
- Conserver les réponses, références et éventuels fichiers sous un identifiant de scénario stable.
- Laisser une personne relire chaque critère ; enregistrer ce qui manque.
- Modifier seulement les instructions nécessaires, puis vérifier que **les deux modèles** ne régressent pas.
- Mesurer aussi la **durée**, la VRAM, les coûts OpenRouter et le nombre de corrections dans la phase de qualification, avec un journal d'exécution séparé.
- Ne pas allonger les prompts par principe : **moins de répétitions, plus de consignes vérifiables**.

## Limites voulues

La suite **prépare** une évaluation ; elle ne la réalise pas d'elle-même. Aucune requête n'est envoyée à Qwen/DeepSeek, aucun secret n'est stocké dans le dépôt, aucun appel à GitHub ou Podman n'est déclenché. L'évaluation complète et l'ajustement final des prompts sont prévus pour la **dernière phase**, après stabilisation du code et de l'interface.

La règle à respecter est : **l'outil peut vérifier la complétude d'un rapport, pas la vérité des jugements humains qu'il contient**.
