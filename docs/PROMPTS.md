# Consignes pédagogiques et contrôles d'intégration

## État des documents de référence

Cette étape applique les exigences explicites de la demande de continuation:
sept rôles, mentor prioritaire, aide directe, exercices consentis, sources fiables,
explication de la chaîne Terraform/Ansible/CI/CD et contrats techniques stricts.
Elle ne certifie pas encore la conformité textuelle aux prompts V2.3 ni au cahier
des charges V1.5. Les documents suivants n'étaient pas accessibles dans le nouvel
espace de travail, et la conversation récupérée n'exposait aucune pièce jointe:

- `Proposition_Prompts_OpenClaw_Hybride_V2.3_Fiabilite_Explication.zip`
- `Proposition_Prompts_OpenClaw_Hybride_V2.3_Fiabilite_Explication_COMPLET.md`
- `OPENCLAW_LOCAL_FEDORA_Cahier_des_Charges_Architecture_Hybride_V1.5_Liberte_Pedagogique_Sources.pdf`

Pour terminer cette intégration, lire les fichiers réellement fournis, consigner
leurs empreintes SHA-256, confronter les sept prompts et exigences au dépôt et
documenter les adaptations nécessaires aux permissions et schémas du worker.
Ne pas reconstituer leur contenu à partir de leur nom ou d'un résumé. Relancer
les contrôles ci-dessous après chaque adaptation.

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

Le backend reste Ollama/Qwen local, sans secours cloud. Le modèle existant est
`qwen3.5:9b-q4_K_M`: le titre de la conversation ne constitue pas une instruction
de migration vers Q6_K. OpenRouter n'est pas implémenté, aucune clé ni requête
cloud n'est ajoutée. Le plafond demandé de 25 EUR/mois n'autorise aucune dépense.

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

Cette PR dépend de la branche de la PR #31, sans la fusionner. Les workflows
acceptent aussi les PR visant `feat/mentor-*` pour tester cette dépendance.
La fusion et le rapprochement final avec les documents restent à traiter
explicitement; ni la PR #31 ni `main` ne sont modifiés par une fusion.
