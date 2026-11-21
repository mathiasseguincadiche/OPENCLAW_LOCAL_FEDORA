# Stratégie cloud-first et qualification des trois moteurs

[← Architecture hybride](ARCHITECTURE_HYBRIDE.md) · [Sept agents](fiches/07-roles-et-outils.md) · [Recette FinOps](validation/FINOPS.md)

## Objectif métier

L'atelier est conçu pour **apprendre et pratiquer l'InfraOps** (Terraform, Ansible,
Linux, conteneurs, K3s/Kubernetes, observabilité, sauvegardes, restauration).
La priorité opérationnelle est désormais le **duo cloud DeepSeek V4.1 Flash 1017
+ GPT-6.2 Sol** lorsque l'utilisateur a volontairement autorisé le cloud et que
les sources sont publiables. **Qwen 3.5 9B n'est pas indispensable au résultat** :
il conserve une route locale pour le privé, le hors-ligne ou les tâches courtes
qu'il réussit réellement.

Ceci **ne modifie pas le choix de confidentialité** : le chat démarre en local,
le cloud est désactivé à l'installation, aucune bascule locale → cloud n'est
automatique. Le projet exige un consentement explicite lié au digest de ses
sources ; il se met en pause si le filtre ou le budget refuse l'appel.

Il y a **sept rôles**, mais seulement **deux modèles cloud et un modèle local
optionnel du point de vue de l'usage**. Le catalogue exige encore Qwen pour
l'installation : *désinstallation ou passage en véritable cloud-only non
implémentés et soumis à une décision ultérieure*.

## Qui décide de quoi ?

| Axe | Décision | Contrôle |
| --- | --- | --- |
| Confidentialité | Utilisateur : local ou autorisation cloud | Passerelle, accord de projet, filtre |
| Spécialité | Plan approuvé : mentor, recherche, architecture, DevOps, sécurité, rédaction, audit | Outils du rôle inchangés |
| Complexité | Plan approuvé : simple, complex ou critical | Champ facultatif `task_tier` |
| Modèle courant | DeepSeek à faible ou fort effort | Politique déterministe, budget 15 € |
| Contre-expertise | Sol sur révision approuvée, ou revue finale auditeur | Budget 10 €, aucun repli silencieux |
| Validations techniques | Outils déterministes dans un laboratoire rootless | Lancement explicite opérateur |
| Rétention de Qwen | Mesures réelles, puis décision humaine | Aucun retrait automatique |

### Niveaux d'une tâche

Le champ `task_tier` est facultatif, mais doit appartenir strictement à :

- `simple` : une commande, une courte explication, un fichier isolé. **DeepSeek rapide**.
- `complex` : fichiers multiples, dépendances, diagnostic croisé. **DeepSeek soutenu**.
- `critical` : risque de sécurité, résilience, déploiement, suppression ou impact majeur.
  **DeepSeek soutenu pour préparer** ; Sol ne prend la relève que lors d'une
  **révision approuvée** ou de la **revue finale**.

La règle est **indépendante du rôle** pour les traitements cloud courants.
Sans `task_tier`, l'ancienne politique par rôle est conservée pour
compatibilité. Aucune classification par mot-clé du prompt, aucune évaluation
automatique de sa confidentialité et aucune dépense Sol « parce que le texte
semble difficile ».

Exemple d'une tâche dans un plan à faire approuver, à adapter :

```json
{
  "id": "architecture-ops",
  "role": "architecte-solutions",
  "task_tier": "critical",
  "title": "Concevoir le plan de restauration",
  "objective": "Comparer deux options et formaliser les hypothèses",
  "depends_on": [],
  "expected_outputs": ["deliverables/architecture-ops/adr.md"],
  "acceptance_criteria": ["Hypothèses, options, limites et tests décrits"]
}
```

Cette classification n'est **pas** une preuve de criticité, ni une autorisation
de déployer ou de transmettre des secrets. Tout passage au cloud est bloqué
sans consentement préalable. Les agents ne disposent toujours ni de `exec`
ni de `apply_patch` ni d'écriture native.

## Scénarios correspondant aux infrastructures réelles

En plus des sept cas génériques historiques, la commande
`clawfedora-evals --suite infraops --plan` fournit sept cas **publics et
synthétiques** : Terraform/libvirt, Ansible Rocky, Compose/K3s, sécurité
SELinux/firewalld, GitHub Actions/GHCR et restauration PostgreSQL. Les mêmes
règles d'autorisation, de budget et de qualification humaine s'appliquent.
Lire [le cas d'étude OpsDesk](CAS_USAGE_INFRAOPS_OPSDESK.md).

## Évaluer chaque modèle au lieu de lui attribuer arbitrairement un rôle

La répartition est une **hypothèse technique**, pas un classement universel.
Utiliser d'abord les sept cas synthétiques de
[`EVALUATION_AGENTS.md`](EVALUATION_AGENTS.md), puis, si nécessaire,
les dialogues de [`EVALUATION_PEDAGOGIE.md`](EVALUATION_PEDAGOGIE.md).
Pour une comparaison InfraOps utile, ajouter à la campagne des cas publics
identiques : Terraform+Ansible, revue de CI, manifestes K3s, incident de
stockage et restauration PostgreSQL.

Même commit, même suite SHA-256, mêmes fichiers, mêmes consignes, mêmes
versions de modèles et mêmes outils autorisés. Les notes sont attribuées
**après lecture des sorties réelles et vérifications déterministes**. Ne
pas comparer un modèle qui aurait accès à des preuves supplémentaires.

### Comparaison hors ligne des trois modèles

Après les appels réellement consentis et les évaluations humaines,
préparer **hors du dépôt** un fichier JSON avec le format suivant.
Les valeurs sont **illustratives, fictives, non des résultats du projet**.

```json
{
  "classification": "synthetic_public",
  "commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "suite_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "models": {
    "qwen3.5:9b-q4_K_M": [
      {"case_id":"case-one","accepted":true,
       "scores":{"technical":3,"clarity":3,"proof":3,"safety":4},
       "elapsed_ms":1000,"cost_usd":0}
    ],
    "deepseek/deepseek-v4.1-flash-1017": [
      {"case_id":"case-one","accepted":true,
       "scores":{"technical":4,"clarity":3,"proof":4,"safety":4},
       "elapsed_ms":1200,"cost_usd":0.01}
    ],
    "openai/gpt-6.2-sol": [
      {"case_id":"case-one","accepted":true,
       "scores":{"technical":4,"clarity":4,"proof":4,"safety":4},
       "elapsed_ms":1300,"cost_usd":0.02}
    ]
  }
}
```

**Attention :** l'exemple montre **un seul cas**. La commande exige **au
moins quatre cas identiques par modèle** : compléter la suite avec les sorties
et les factures mesurées avant de lancer le comparateur.

```bash
clawfedora-model-qualify /chemin/prive/rapport.json
```

La commande ne lance aucun modèle, n'appelle aucune API et ne vérifie pas
la sincérité des notes humaines. Elle refuse les mesures absentes,
les ensembles de cas différents, les identifiants inconnus et les montants
invalides. Son verdict est **un signal de revue**, jamais une désinstallation.

### Critère de maintien du local

Conserver Qwen **seulement si** des cas InfraOps réels démontrent une valeur
supplémentaire : résultats techniquement acceptables et une contribution
significative (confidentialité indispensable, disponibilité hors API,
économie réellement utile ou délai raisonnable).

Si Qwen n'apporte aucun avantage convaincant, **ne plus l'utiliser dans les
workflows**, puis prévoir une migration cloud-only séparée qui retire
proprement les dépendances Ollama/GPU, les contrats d'installation et les
parcours locaux. Cette migration doit préserver les refus de confidentialité :
une tâche privée ne doit jamais être envoyée au cloud par défaut.

## Laboratoire InfraOps

Le programme `clawfedora-lab` préexiste : il demande une confirmation
`--apply`, n'utilise qu'une image locale épinglée par digest, copie un
snapshot restreint, et lance Podman rootless sans réseau ni écritures sur
la source. Il **ne donne aucun droit `exec` aux agents**.

Cette évolution ajoute `kubeconform` aux validateurs possibles. Seuls les
YAML placés sous `k8s/`, `kubernetes/` ou `manifests/` sont inspectés ;
le programme passe `-schema-location /schemas` et n'utilise **jamais**
la source distante implicite. L'image immutable doit donc contenir
**Kubeconform et des schémas Kubernetes compatibles dans `/schemas`**.
Si l'image ne les contient pas, la vérification ne peut pas être déclarée réussie.

```bash
# Simulation : aucune commande ni image lancée.
clawfedora-lab --project ./mon-projet --tool kubeconform

# Validation volontaire, image locale préinstallée et vérifiée.
clawfedora-lab --project ./mon-projet --tool kubeconform \
  --image registry.example.org/validators@sha256:<DIGEST_COMPLET> --apply
```

Le digest doit être remplacé par celui d'une image **réellement construite,
installée et auditée**, pas par un digest fictif. Les résultats de tests du
dépôt ne prouvent pas que le laboratoire tourne sur le PC cible. Le mode
rootless/SELinux, la VRAM B580, la latence, les fournisseurs et la qualité
de Qwen restent à qualifier.

## Critères d'acceptation

1. CI et contrôles statiques réussis sur le commit exact.
2. Aucune régression des autorisations, du filtre, des budgets ou des consentements.
3. Comparaison sur de vraies sorties, avec notes et coûts justifiés.
4. Vérification de bout en bout du laboratoire sur Fedora après installation.
5. Décision explicite et réversible avant toute suppression de Qwen.

**Statut : implémentation préparatoire, non recette réelle sur le PC.**
