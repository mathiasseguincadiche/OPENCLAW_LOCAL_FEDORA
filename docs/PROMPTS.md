# Consignes pédagogiques et contrôles d'intégration

[← Guide pour commencer](GUIDE.md) · [Les sept agents expliqués](fiches/07-roles-et-outils.md) · [Architecture](fiches/11-comment-ca-marche.md)

**Ce document est une trace technique des décisions sur les consignes (prompts) et de leurs
contrôles.** Il ne remplace pas les fiches pédagogiques : leurs exemples expliquent le
comportement attendu, tandis que `agents/` et `config/core/tool_policy.yaml` fixent
ce que le modèle reçoit réellement et les outils qu'il peut employer.

## Documents de référence et confrontation

Les documents de référence ont été lus en entier le 9 octobre 2026 :

| Document | SHA-256 |
|---|---|
| `Atelier_IA_Hybride_Openclaw.pdf` (cahier des charges V1.5, 38 pages) | `6a703eaef0e4d1372bdfc523f94855d58ded388e678e3728f24e525a14efd536` |
| `Proposition_Prompts_OpenClaw_Hybride_V2.3_Fiabilite_Explication.zip` (33 fichiers) | `19a9294ee013b823334b5d9cc33f443004dcde831c5ae62ad1a301bd16148c2e` |

Le fichier `..._V2.3_..._COMPLET.md`, cité par le PDF, n'a pas été fourni et n'a pas été lu.
Ces documents ne sont pas ajoutés au dépôt : seules leurs empreintes y figurent.

Le zip décrit des prompts plus longs, écrits sans le code actuel sous les yeux. Le remplacer
tel quel aurait perdu des accroches du moteur (`source_coverage`, `context/exchange/`,
`drawio_reference`, `writing_scope`, `practice_opt_in`) et fait dépasser 12000 caractères
au chef (11743 mesurés sur le zip brut, soit 257 de marge). La fusion est donc sélective :

| Élément V2.3 | Décision |
|---|---|
| Mentor d'abord, coordinateur ensuite ; pas d'exercice imposé | Repris (déjà présent, renforcé) |
| Vulgarisation en couches, chaîne de A à Z, « pas d'ordre universel » | Repris, condensé dans `PEDAGOGY.md` |
| Direct = co-construction (livrable complet expliqué bloc par bloc) | Ajouté |
| Étiquettes OBSERVÉ / VÉRIFIÉ / PROPOSÉ / NON VÉRIFIÉ, portée de `terraform validate`, idempotence Ansible | Ajouté au CONTRACT (règle 4) |
| Fraîcheur des sources (30 jours, version visée, sources secondaires non normatives) | Repris (règle 18) ; seules des URL réellement renvoyées par un outil sont citables |
| Ne jamais recopier un secret rencontré | Ajouté (règle 9) |
| Mentions du routeur cloud, du budget de 25 € et du middleware comme s'ils existaient | **Non reprises** : les prompts restent vrais quel que soit le modèle (règles 5 et 20). Un test interdit « Qwen », « OpenRouter », « GLM », « DeepSeek » dans les consignes. |
| `IDENTITY.md`, `SOUL.md`, `HEARTBEAT.md` | Repris tels quels |
| Méthode détaillée de chaque rôle | Reprise, sans les paragraphes « contrat technique » répétés dans chaque rôle (factorisés dans `TOOLS.md` et `CONTRACT.md`) |
| Suivi de compétences, révisions espacées, laboratoire, Skills | Hors périmètre de ce lot (voir `PLAN_MIGRATION_HYBRIDE.md`) ; les consignes disent qu'aucun rappel ni mémoire automatique n'existe |

Tailles mesurées lors de la fusion V2.3 initiale (unités UTF-16 d'OpenClaw, limite 12000) : de 11158 (recherche) à
11543 (chef, DevOps), soit au moins 457 de marge. Le chef avec l'historique maximal du chat
atteint 21684 tokens estimés sur 32768 de contexte, sortie de 4096 comprise.

La conformité textuelle n'est pas une preuve de comportement : la qualité des réponses des modèles
reste à observer à l'usage.

## Consignes réellement injectées

`effective_instructions` dans `src/clawfedora/agents.py` compose un seul fichier
`AGENTS.md`, dans cet ordre:

1. `agents/_shared/PEDAGOGY.md`
2. `agents/<rôle>/AGENTS.md`
3. `agents/_shared/TOOLS.md`
4. `agents/_shared/CONTRACT.md`

Chaque partie est débarrassée de ses blancs de bord; deux sauts de ligne séparent
les parties, et le fichier finit par un saut de ligne. La limite de 12000 porte
sur le fichier assemblé, séparateurs inclus. Le validateur utilise les unités
UTF-16 d'OpenClaw: un emoji hors du plan Unicode de base compte pour deux unités,
même si Python le compte comme un caractère. Cette mesure garantit aussi au plus
12000 caractères Python. Augmenter le budget déclaré au-delà de 12000 est refusé.

`IDENTITY.md`, `SOUL.md`, `TOOLS.md` et `HEARTBEAT.md` sont aussi injectés séparément
par OpenClaw. Leurs limites individuelles et la somme de tous ces fichiers avec
`AGENTS.md` sont vérifiées avant toute écriture de workspace. La somme doit rester
dans `bootstrap_total_max_chars` (24000). Le contrôle natif vérifie la présence
intégrale du fichier assemblé dans la requête envoyée à Ollama, les permissions
des outils réellement exposés et le contexte, y compris avec l'historique maximal.

## Cohérence entre Qwen local et DeepSeek cloud

Les consignes communes doivent rester **indépendantes du fournisseur**, car les sept rôles peuvent être exécutés sur les deux routes. Elles ne doivent donc plus annoncer systématiquement un contexte de 32 768 tokens ou une sortie maximale de 4 096 tokens : ces valeurs correspondent **au modèle local** ; la route cloud a d'autres limites, imposées et vérifiées par le code.

La règle pédagogique a été précisée : **trois notions nouvelles par séquence guidée**, mais aucune limite arbitraire à la profondeur d'une **explication directe demandée**. Le contexte, les droits aux outils, l'accord cloud et le budget restent définis par l'application, jamais par un prompt.

Les valeurs actuelles sont dans `config/core/openclaw_policy.yaml` et `config/core/cloud_policy.yaml`, non dans les fichiers `agents/_shared/`. La qualité réelle doit être contrôlée sur les scénarios d'évaluation, pas déduite de la formulation des instructions.

## Ajustement du 20 octobre 2026 — pédagogie et sobriété

Les consignes communes renforcent la réponse utile et l'exemple **court, concret et vérifiable** dans Linux/OPS. Le mentor évite une délégation superflue ; le rédacteur supprime les répétitions sans omettre le diagnostic, les risques ou le rollback. Ces règles sont **indépendantes du fournisseur** ; elles concernent Qwen et DeepSeek V4.1 Flash 1017. Elles ne demandent ni quiz imposé ni réponse volontairement incomplète.

**Qualification à faire avec des appels réels :** utiliser les mêmes demandes publiques sur les deux routes, par exemple : expliquer `terraform plan` versus `apply`, diagnostiquer un journal GitHub Actions synthétique, relier Ansible à une VM Rocky Linux, décrire un rollback et le rôle des secrets. Comparer exactitude, clarté, exemples, vérifications, nombre de tours, tokens et coût. La grille par rôle existante reste dans la suite d'évaluation du dépôt. Ces mesures ne sont **pas encore réalisées** sur Fedora.

Pour économiser des tokens cloud, l'opérateur peut choisir **manuellement** `equilibre` (medium / 8192 tokens de sortie maximum), après installation : `./menu.sh --action cloud-set-profile --value equilibre --apply`. `approfondi` (xhigh / 32768) reste le défaut historique et se réactive sur les incidents difficiles. Il s'agit de plafonds, pas de budgets consommés automatiquement. Les vérifications restent obligatoires même lorsqu'on cherche une réponse concise.

## Liberté pédagogique

Le chef-operations est d'abord le mentor, puis le coordinateur. Une explication
en chat n'exige ni projet, ni exercice, ni fiche mentor préalable. Pour les
nouveaux projets, `direct` est le défaut. En `adaptive`, le modèle peut suggérer
`guided`, mais l'utilisateur seul approuve `practice_opt_in=true` pour la tâche.
Un mode global `guided` explicitement choisi reste applicable. Les contrats
historiques approuvés conservent leurs règles; aucune migration silencieuse.

Pour une demande de chaîne complète, les consignes relient le besoin au dépôt,
à la CI, au provisionnement, à la configuration, à la CD puis à l'observation et
au retour arrière. Chaque passage doit préciser ses entrées, ses fichiers, ses
sorties, ses hypothèses et la vérification attendue. L'explication peut être
découpée pour tenir dans le contexte; le découpage ne devient pas un exercice.

Points documentaires pour la relecture, consultés le 8 octobre 2026:

- [Terraform plan, documentation HashiCorp](https://developer.hashicorp.com/terraform/cli/commands/plan):
  prépare les changements proposés; leur application est une étape distincte.
- [Environnements de déploiement, documentation GitHub](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments):
  les jobs peuvent référencer un environnement pour encadrer les déploiements.

Les prompts demandent une source officielle adaptée à la version utilisée,
son URL, sa date de consultation, le passage effectivement lu et ses limites.
La présence de ces consignes ne garantit pas que Qwen les suivra: une recette
avec le modèle local reste nécessaire.

## JSON, permissions et backend

En chat, la réponse est du texte français naturel. Pour une tâche de projet,
le worker attend uniquement `files` et `summary`, avec les chemins exacts du
schéma et des contenus non vides. Feedback et audit conservent leurs schémas
spécifiques. Les clés dupliquées, `NaN` et les infinis sont rejetés sans réparation
automatique. La réparation de syntaxe existante reste bornée et locale.

Le validateur compare les permissions de chaque rôle aux outils métier réellement
déclarés. Les outils d'exécution, d'écriture native, de publication et de
délégation restent interdits. Le plugin géré peut produire les artefacts autorisés;
le collecteur publie uniquement les sorties prévues dans le projet.

Le backend de ce lot reste Ollama/Qwen local, sans secours cloud. Le modèle existant est
`qwen3.5:9b-q4_K_M`. Le cloud (OpenRouter) fait l'objet des lots suivants du plan
`docs/PLAN_MIGRATION_HYBRIDE.md` (lot 1) : aucune clé ni requête cloud n'est ajoutée ici.
Les consignes ne mentionnent aucun modèle précis, pour rester exactes après cette migration.

## Pédagogie multi-tours — version fusionnée

Le contrat commun demande désormais de changer d'angle quand l'utilisateur ne comprend pas (comparaison, contre-exemple, mécanisme), plutôt que de répéter mot pour mot ; le pont Open WebUI ajoute la même instruction en conversation. Cette directive est **indépendante de Qwen et DeepSeek**. La fiche mentor intègre les préférences `explanation_style` et `learning_summary` approuvées, transmises comme informations d'adaptation et jamais comme preuve de compétence.

La nouvelle commande `clawfedora-pedagogy --plan` expose quatre conversations DevOps synthétiques de trois tours, tandis que `--report` / `--compare` valident des notes humaines sur 20. Ce logiciel ne réalise aucune évaluation automatique de Gemini et ne prouve pas une note maximale ; [protocole](EVALUATION_PEDAGOGIE.md). Les prompts complets restent sous `bootstrap_max_chars: 12000` défini dans `config/core/openclaw_policy.yaml`.

## Vérification

```bash
make ci
make native-schema
make native-prompt
make native-tools
```

Les tests couvrent notamment les sept fichiers déployés, l'ordre d'assemblage,
les frontières 12000/12001 avec caractères accentués et emoji, la croissance des
parties partagées, la limite totale, les permissions par rôle, les flags locaux,
le consentement pédagogique et les sorties JSON. Le contrôle natif emploie le
vrai OpenClaw verrouillé et un faux endpoint Ollama local; il ne charge aucun
modèle et ne mesure ni qualité pédagogique, ni GPU, ni déploiement réel.

Ces contrôles ont été repris dans `main` par le lot 2 du plan hybride (PR #34).
Les PR #31 et #32, qui les avaient introduits, ont été fermées sans fusion : leur
contenu utile est repris et tracé dans ce document. Les workflows ne ciblent plus
que `main`.
