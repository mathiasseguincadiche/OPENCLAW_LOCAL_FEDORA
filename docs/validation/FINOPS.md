> **Archive de conception 2026.** Recette de facturation du fournisseur OpenRouter retiré. Ce test n'appartient plus à la réception active de l'atelier exclusivement local. Voir [architecture locale](../ARCHITECTURE_LOCALE_QWEN_ORNITH.md).

# Recette finale FinOps — atelier hybride

**Statut : protocole de réception, pas un résultat de réception.** Aucun
appel réel n'est déclenché par ce document ni par le comparateur hors ligne.
Le cloud reste facultatif, désactivé par défaut. Ne pas engager de frais
ou transmettre des sources sans accord explicite.

## 1. Référence et critères de réception

| Domaine | Contrôle de dépôt | Réception réelle restante |
| --- | --- | --- |
| Budget | Réservation avant appel, plafond global 35 €, enveloppes 15/10 €, réserve 10 € non routable | Crédits prépayés, frais et relevé rapprochés |
| Routage | Sept rôles, quatre alias automatiques, aucun repli local vers cloud | Vérifier modèle et effort dans l'activité réelle |
| Contexte | Extraits avec SHA-256, historique compact | Vérifier les sources et la couverture d'une tâche longue |
| Cache | Compteurs disponibles et ratio apparié | Mesurer à chaud/froid, sans supposer d'économie |
| Prompts | Taille UTF-16 et injection native | Évaluer les sept rôles sur les mêmes énoncés |
| Audits | Précontrôle, preuves, bundles, scellés | Réception d'un dossier DevOps réel approuvé |

Partir d'un commit Git identifié et d'une CI complète verte. Les scénarios
synthétiques ne prouvent pas le déploiement d'une infrastructure. Pour la
machine, suivre [la réception Fedora](../RECEPTION_ETAPE3.md).

## 2. Préparer sans dépenser

```bash
git rev-parse HEAD
./menu.sh --action quick-check
./menu.sh --action cloud-status
clawfedora-evals --plan
clawfedora-evals --inputs-only
clawfedora-pedagogy --plan
```

Les deux dernières suites ne lancent aucun modèle. `quick-check` peut lancer
une génération locale. Conserver hors dépôt le SHA Git, l'empreinte
`suite_sha256` du plan, les profils, versions et relevés expurgés.
Ne pas partager les clés, identifiants personnels ni sources privées.

## 3. Vérifier une route cloud à coût limité

Uniquement après l'installation et consentement : prépaiement sans recharge,
limite de clé selon [la fiche cloud](../fiches/12-cloud.md), journal rapproché.
Commencer par DeepSeek. Une question publique puis une tâche avec outil suffisent
au test de fumée. Vérifier le statut, l'activité OpenRouter, les compteurs et la
provenance. Les générations d'outils peuvent facturer plusieurs appels.

- Mode auto : DeepSeek en routine ; Sol lors des révisions approuvées et de la
  revue finale (la recherche reste sur DeepSeek).
- Mode manuel : sélectionner explicitement un modèle et un effort pour isoler
  un essai ; revenir à auto après. Ne pas modifier le mode pendant une génération.
- Refus de données ou budget : aucun nouvel appel à un autre modèle cloud.
  En projet, pause visible ; en chat, comportement local visible selon politique.
- Cache : comparer deux demandes publiques identiques en sessions séparées avec
  même modèle, profil et préfixe. Lire `CLOUD_CACHE` et `reported_calls` ;
  un ratio absent ne prouve pas qu'il est nul. Le fournisseur peut varier ;
  ne pas promettre un cache hit. Ne pas ajouter de données seulement pour le cache.

## 4. Mesurer le coût par tâche acceptée

Optionnel après le test de fumée. Fixer le même commit, les sept énoncés et la même
grille d'acceptation avant de comparer. Utiliser les deux modèles en mode manuel,
avec efforts notés par scénario ; garder séparés les résultats. Un échec compte
dans le coût, même sans livrable accepté. Arrêter si le budget ou le consentement
ne permet plus de continuer : un rapport incomplet reste incomplet.

Compléter les deux rapports humains décrits dans
[l'évaluation des agents](../EVALUATION_AGENTS.md) avec, à la racine :

- `route: "cloud"`, `model_id` exact, `commit` (40 caractères hexadécimaux),
  `suite_sha256` (valeur de `--plan`).
- Pour chaque résultat, `measurement` ci-dessous.

Exemple de structure **fictive**, pas une mesure exploitable :

```json
{
  "accepted": false,
  "profile": "high",
  "cost_microusd": 1250,
  "calls": 2,
  "elapsed_ms": 15400,
  "billing_reference": "releve-local-expurge/cas-01"
}
```

1 USD = 1 000 000 micro-USD. Additionner tous les appels facturés du scénario
(y compris reprises et échecs) puis arrondir au micro-USD supérieur ; zéro
seulement si effectivement constaté. Rapprocher les appels avec l'activité
fournisseur et le journal local ; si l'attribution est incertaine, ne pas
inventer la mesure. La durée couvre le scénario entier et ses reprises.
`accepted` est une décision humaine justifiée par les notes et preuves,
pas un score produit automatiquement. Conserver les mesures hors dépôt.

```bash
clawfedora-evals --finops-compare notes_flash.json notes_sol.json
```

Le rapport agrège les notes, les appels, les durées et les coûts déclarés.
Coût unitaire = coût de **tous** les scénarios / nombre de tâches acceptées
(arrondi au micro-USD supérieur). Aucune acceptation : coût unitaire indéfini.
Le comparateur refuse des suites, commits ou modèles différents et des mesures
absentes. Il ne lit pas l'API, ne valide pas les références de facturation,
ne convertit pas en euros, ne certifie ni les notes ni l'exécution technique,
et ne sélectionne pas automatiquement un vainqueur.

## 5. Décider après les mesures

Préserver DeepSeek en routine si les preuves et la qualité répondent au besoin ;
réserver Sol aux cas où il réduit les reprises ou apporte une contre-expertise
utile. Une seule campagne ne prouve pas une supériorité générale. Noter les
limites, l'état de la confidentialité, les écarts de facturation et les scénarios
non exécutés. Aucun changement automatique de budget ou de modèle.

[← Validation](README.md) · [Fiche cloud](../fiches/12-cloud.md)
