# Plugins métier légers pour Fedora

Le SDK OpenClaw appelle un plugin natif local, `clawfedora-toolkit`, explicitement autorisé par rôle. Ce n’est pas une collection de prompts ni un terminal général. Le plugin existant est enrichi, sans second orchestrateur, serveur MCP permanent, modèle d’embeddings ou modèle IA supplémentaire.

## Ce qui est intégré

| Spécialiste | Outils disponibles et usage |
|---|---|
| Mentor infrastructure/OPS | recherche locale, trame brief, rapports CI, disponibilité des outils; le moteur gère les dépendances |
| Recherche | lecture/PDF/images, recherche web autorisée et recherche locale avec provenance |
| Architecte | trame ADR, schéma structuré → Draw.io éditable + aperçu SVG local |
| DevOps | ShellCheck pour Bash, yamllint pour YAML, PyMarkdown pour ses runbooks, parsing JSON/Python |
| Sécurité | Gitleaks pour les secrets du texte fourni, ShellCheck/yamllint et contrôles OPS existants |
| Rédacteur pédagogique | trames guide/explication et PyMarkdown pour la forme des documents |
| Auditeur | les mêmes contrôles statiques et lecture des preuves, sans corriger les livrables |

`clawfedora_lint(format, content)` choisit parmi les formats autorisés du rôle: `shell`, `yaml`, `markdown`, `secrets`. Entrée 12 Ko, délai 5 secondes par commande, rapport court, aucune exécution du script ou déploiement. `clawfedora_tool_status` expose ce qui est effectivement présent. Un binaire absent donne **UNAVAILABLE**, jamais un PASS supposé.

ShellCheck et Gitleaks proviennent des paquets Fedora du bootstrap. Les petites dépendances Python yamllint 1.38.0 et PyMarkdown 0.9.40 sont figées dans la venv gérée. Pas de daemon: elles consomment lors de l’appel. Les mises à jour des paquets Fedora restent du ressort du système; la version réellement utilisée est enregistrée pour les linters. Sur une ancienne installation, la migration sauvegardée réapplique le bootstrap.

## Limites d’exécution et preuves

Le helper reçoit un workspace géré et le rôle fourni par OpenClaw. Il fixe l’interpréteur et les commandes; aucun choix d’exécutable, argument libre, chemin système, jeton cloud ou URL à télécharger ne vient du modèle. Les linters travaillent en répertoire temporaire, sans configuration ni plugins issus du projet, et les directives de désactivation sont ignorées. Le schéma Draw.io est construit depuis des libellés/indices bornés, avec styles et géométrie fixes: aucun XML libre du modèle, image externe, lien ou script. Le SVG initial reprend les mêmes blocs et connexions. Graphviz n’est plus requis ni installé par le bootstrap; aucun paquet existant n’est désinstallé.

Pour le lint et les schémas, le helper écrit un reçu généré sous `.clawfedora-tool-evidence` du workspace. Il conserve statut, version, hash du texte et résultat réel. Le worker copie ses nouveaux reçus dans `evidence/<task>/tool-*.json`, après le contrôle d’intégrité; le modèle ne choisit pas le chemin. Les sources .drawio et aperçus .svg restent dans des fichiers générés; le modèle retourne drawio_reference et svg_reference pour les sorties attendues. Le worker vérifie chaque hash et collecte ces fichiers sans exiger la réécriture du XML dans les 1024 tokens. Les anciens contrats .svg restent compatibles. [DRAWIO.md](DRAWIO.md) décrit le téléchargement, l’édition et la reprise du brouillon. Dans un chat, le reçu reste dans le workspace et aucun projet n’est modifié. Gitleaks retourne uniquement identifiant de règle et ligne, jamais les secrets ou son rapport brut.

Le reçu d’une amorce ne valide pas le fichier complété ensuite: **le hash doit correspondre au contenu contrôlé**. Les linters vérifient forme/syntaxe, Gitleaks des secrets du texte fourni. Aucun de ces PASS ne prouve une restauration, un déploiement, une configuration métier correcte ou une sécurité exhaustive. Les tests réels sont exécutés par l’apprenant dans son exercice/CI qualifié.

## Interpréter les résultats de l’exercice

clawfedora_ci_report est disponible aux sept rôles. Il interprète un JSON Terraform ou un résumé CI borné, sans recopier les journaux bruts. Les statuts restent déclarés, avec verification UNVERIFIED: il n’exécute ni n’authentifie un pipeline. [INFRASTRUCTURE_CHECKS.md](INFRASTRUCTURE_CHECKS.md) décrit les formats et les vérifications de provenance.

## Ajouter les outils plus avancés au moment utile

Terraform `fmt`/`validate`, ansible-lint, validation Compose/Kubernetes, Trivy et scans de dépendances apportent une valeur dans leurs exercices. Ils ne sont pas tous installés ni appelables par ce plugin. Les ajouter d’abord à la CI du projet concerné, avec versions/images figées, résultats et limites lisibles; les exposer ensuite si un usage répété justifie un runner isolé.

`terraform validate` requiert notamment les modules/providers installés: le mot «validate» ne dispense pas de maîtriser les exécutables de providers. ansible-lint utilise un environnement Ansible et ses extensions. Ces contraintes rendent un wrapper générique sur le poste personnel peu adapté. Un futur runner doit isoler réseau, credentials, montages et ressources plutôt que simplement donner exec à l’agent. Trivy/config et un contrôle de schéma Kubernetes ne constituent pas un déploiement testé.

Sources consultées en octobre 2026: [SDK plugins OpenClaw](https://docs.openclaw.ai/plugins/building-plugins), [ShellCheck](https://github.com/koalaman/shellcheck), [yamllint](https://yamllint.readthedocs.io/en/stable/), [PyMarkdown](https://pymarkdown.readthedocs.io/en/latest/), [format Draw.io](https://www.drawio.com/docs/reference/diagram-generation/), [Gitleaks Fedora 44](https://packages.fedoraproject.org/pkgs/gitleaks/gitleaks/), [Gitleaks](https://github.com/gitleaks/gitleaks), [Terraform validate](https://developer.hashicorp.com/terraform/cli/commands/validate), [ansible-lint](https://docs.ansible.com/projects/lint/usage/).
