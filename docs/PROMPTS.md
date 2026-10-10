# Consignes pédagogiques et contrôles d'intégration

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

Tailles mesurées après fusion (unités UTF-16 d'OpenClaw, limite 12000) : de 11158 (recherche) à
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
