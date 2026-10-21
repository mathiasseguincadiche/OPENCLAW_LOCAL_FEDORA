# Qualification pédagogique : objectif 20/20, sans inventer de résultat

[← Évaluation des sept agents](EVALUATION_AGENTS.md) · [Apprendre](fiches/05-apprendre.md) · [Modèle cloud](DECISION_MODELE.md)

L'atelier possède **deux suites complémentaires**. La suite technique historique
(clawfedora-evals) juge les sept rôles sur quatre aspects professionnels, de 0 à 4.
La nouvelle suite pédagogique (clawfedora-pedagogy) juge **des conversations multi-tours**
selon les quatre attentes de l'utilisateur, chacune sur **5 points** :

| Critère | Ce que signifie 5/5 |
| --- | --- |
| Clarté | Explication adaptée, compréhensible et concrète, sans jargon gratuit |
| Profondeur | Pourquoi/comment, causalité, chaîne d'outils, risques et vérifications |
| Interactivité | Reformulation après incompréhension, réponse ciblée, cohérence sur les tours |
| Exactitude | Faits techniques exacts, sources utiles, incertitudes et preuves honnêtes |

**Cible : 20/20 global et 5/5 dans chaque critère.** Une note n'est jamais une
garantie de réponse parfaite sur tous les sujets.

## 1. Consulter les scénarios sans dépenser

```bash
clawfedora-pedagogy --plan
```

Quatre scénarios synthétiques sont versionnés dans
`config/evals/pedagogy_conversations.yaml`, avec **trois questions successives**
pour chaque conversation : idempotence Ansible/Bash/Rocky, Terraform Azure,
diagnostic GitHub Actions et sécurité CI AWS.

## 2. Tester des échanges réels, à protocole égal

Pour chaque scénario : ouvrir une session vierge, sélectionner le rôle prévu,
poser les questions **dans l'ordre**, copier chaque réponse intégralement et noter
les limites observées. Répéter avec le même contexte et les mêmes questions :

- Qwen local ;
- DeepSeek 1017 **uniquement si le cloud a été activé volontairement** et si
  les crédits prépayés et la confidentialité l'autorisent ;
- éventuellement Gemini en application extérieure, comme **référence manuelle**
  sans clé ni route Gemini intégrée au dépôt.

Ne pas transmettre de secrets, d'extraits d'entreprise ou de documents privés
aux fournisseurs externes. Conserver les réponses et les observations localement
en dehors de Git ; ne jamais publier une conversation privée.

## 3. Renseigner un rapport humain

Créer un JSON avec `route` : `local`, `cloud` ou `reference` ;
`results` doit couvrir les quatre scénarios. Chaque entrée contient :

```json
{
  "scenario": "ansible-idempotence",
  "reviewer": "evaluateur-humain",
  "notes": "Analyse détaillée du dialogue, des confusions et des corrections.",
  "evidence": ["notes-privees/ansible-idempotence"],
  "dialogue": [
    {"user": "Question exactement reprise du scénario #1", "assistant": "Réponse du modèle #1"},
    {"user": "Question exactement reprise du scénario #2", "assistant": "Réponse du modèle #2"},
    {"user": "Question exactement reprise du scénario #3", "assistant": "Réponse du modèle #3"}
  ],
  "scores": {"clarity": 4, "depth": 5, "interaction": 4, "accuracy": 5},
  "usage": {"input_tokens": 1234, "output_tokens": 800, "cost_usd": 0.003}
}
```


Les trois questions `user` doivent être recopiées **à l'identique** depuis
le plan ; les réponses sont celles **réellement obtenues**. Chaque entrée comporte
un examinateur, une justification et au moins une référence à une preuve. `usage`
est **facultatif** ; ne pas le renseigner lorsque les données ne sont pas mesurées.
**Les valeurs ci-dessus ne sont qu'un exemple de structure fictif et incomplet.**

```bash
clawfedora-pedagogy --report ./revue_deepseek.json
clawfedora-pedagogy --compare ./revue_deepseek.json ./revue_gemini.json
```

La différence par critère et sur 20 résume les évaluations humaines.
La commande ne contacte **aucune API**, ne note aucun modèle automatiquement et ne
vérifie ni les chiffres tarifaires déclarés ni la véracité des justifications.

## 4. Continuité et style sans nouvel abonnement

Dans le tableau de bord, rubrique « Mon accompagnement et la continuité du chat »,
l'utilisateur peut désormais préciser **sa manière préférée d'apprendre**
et **les connaissances à conserver de ses échanges**. Ces deux notes sont bornées
à 500 caractères, enregistrées uniquement sur approbation explicite,
réinjectées au mentor et jointes aux projets approuvés. La session n'invente
pas de mémoire ; aucune IA n'enregistre silencieusement de notes.

Si tu dis « je n'ai pas compris », les consignes du chat et des agents demandent
de changer d'angle, de comparer ou de donner un contre-exemple, plutôt que répéter.
Ce sont des comportements **souhaités**, pas une certification de qualité avant
les conversations réelles.

## 5. Conditions d'acceptation et lecture du résultat

L'objectif n'est considéré comme **observé** que si chaque critère obtient 5/5 **sur les réponses réellement enregistrées**, relues avec des sources attribuables. Noter explicitement les points de confusion, les citations inexactes, les répétitions et les corrections obtenues aux tours 2 et 3 ; garder un exemple d'échec pour calibrer les évaluateurs. Les notes sont subjectives, même avec une grille structurée : plusieurs scénarios et si possible plusieurs relecteurs indépendants réduisent ce biais sans l'annuler.

Les deux suites restent distinctes : `clawfedora-evals` vérifie les sept rôles sur leurs pratiques professionnelles ; `clawfedora-pedagogy` observe les quatre qualités de conversation. Une CI verte ne calcule pas de note pédagogique.

## 6. Coût, vérification et limites

Le plafond cloud reste 25 €/mois, avec activation explicite et profils
`rapide`, `equilibre` et `approfondi`. Aucun troisième fournisseur n'a été ajouté,
et cette suite d'évaluation n'entraîne aucun appel facturé. Ne jamais alléger
le filtrage pour faire fonctionner un modèle ou un outil.

Les contrôles automatisés vérifient le **format** des rapports et des consignes.
La qualité réelle d'OpenRouter/DeepSeek, la fluidité de la conversation
et le niveau atteint face à Gemini sont **à qualifier sur Fedora**.
