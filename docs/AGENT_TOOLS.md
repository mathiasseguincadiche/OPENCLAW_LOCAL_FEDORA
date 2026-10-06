# Six rôles, outils effectifs et apprentissage DevOps infrastructure/OPS

L’architecte assure la synthèse finale et la pédagogie d’ensemble. Le DevOps rédige procédures, configurations, stratégies d’exploitation et rollback; l’expert recherche fournit les sources et mécanismes; la sécurité explique les risques; l’auditeur vérifie preuves, cohérence et actionnabilité. Le chef cadre et ordonne le travail. Cette répartition évite un septième rédacteur permanent et une duplication de chaque livrable.

| Rôle | Responsabilité et production | Outils spécifiques |
|---|---|---|
| Chef des opérations | Cadrage, questions, plan court et critères de fin | Trame `brief`; inventaire et historique des sessions autorisées |
| Expert recherche | Sources primaires datées, mécanismes, alternatives et limites | Trame `sources`; recherche et lecture web |
| Architecte solutions | ADR, architecture, flux, schémas et rédaction finale progressive | Trames `adr`/`guide`; schéma SVG et Mermaid |
| Ingénieur DevOps infrastructure/OPS | Runbooks, scripts proposés, configuration, diagnostic, déploiement et Git/CI | Trames `runbook`/`incident`; contrôles statiques JSON/YAML/Python/texte |
| Ingénieur sécurité | Scénarios de menace, droits, exposition, contrôles et risque résiduel | Trame `threats`; contrôles statiques et alertes OPS |
| Auditeur qualité | Critères, sources, intégrité, preuves et pertinence pédagogique | Trame `audit`; contrôles statiques; lecture directe des originaux |

Tous ont `read`, `pdf`, `view_image`, `session_status`, les outils web autorisés, `clawfedora_search` et `clawfedora_outline`. Les habilitations effectives sont dans `config/core/tool_policy.yaml`; le helper vérifie aussi le rôle et le workspace géré. Le schéma est réservé à l’architecte; les contrôles de code à DevOps/sécurité/audit. L’IA ne choisit ni l’exécutable ni le module Python appelé.

## Ce qui fonctionne réellement

Le plugin local `plugins/clawfedora-toolkit` est chargé par OpenClaw; les outils sont optionnels et explicitement autorisés par rôle. Il appelle un module Python fixe de la venv gérée, sans shell, avec délai 10 secondes et entrées/sorties bornées. Il n’ajoute ni service ni modèle.

- `clawfedora_search(query, scope)`: au plus quatre passages de fichiers texte du workspace, avec chemin et numéro de ligne. Choisir le snapshot de la tâche comme scope. Scan borné (200 fichiers, 2 Mo), pas d’embeddings ni promesse d’exhaustivité. Aucun accès aux dossiers d’un autre rôle.
- `clawfedora_outline(kind, title)`: trame spécifique au métier, avec rubriques et emplacements à compléter. Ce n’est ni une documentation achevée ni une preuve.
- `clawfedora_diagram(nodes, edges)`: jusqu’à huit composants et douze liens, libellés échappés, SVG inerte et source Mermaid. Aucun navigateur, script, URL externe ou Graphviz. Pour le budget de sortie, préférer des schémas très courts ou la source Mermaid.
- `clawfedora_check(format, content)`: parsing JSON/YAML/Python et quelques alertes sur des propositions OPS. Aucun code exécuté. `runtime_tested=false` reste explicite; aucune garantie de sécurité, conformité métier, type checking, syntaxe shell ou fonctionnement Terraform/Kubernetes. Pour ces besoins, prévoir une exécution qualifiée séparément.

Les outils retournent leurs résultats. Pour un projet, l’agent inclut les documents dans le JSON `files` demandé; **seul le collecteur écrit les chemins attendus** `deliverables/<task-id>/...`, `diagrams/<task-id>/...`, etc. La capacité d’écriture fictive `architecture_scoped` a été supprimée des prompts. Les écritures natives et `exec/process` restent interdites. Dans un chat libre, le résultat peut être présenté dans la réponse mais n’est pas livré automatiquement dans un projet.

## Un exemple de plan proportionné

Pour choisir et documenter une stratégie de sauvegarde Fedora:

1. Recherche seulement si les informations nécessaires sont absentes ou doivent être actualisées.
2. Architecte: comparer deux options et proposer un ADR court.
3. DevOps: proposer une procédure de sauvegarde/restauration et les résultats à vérifier; dépend du choix d’architecture.
4. Architecte: synthèse finale pédagogique, réutilisant ADR et procédure. Ajouter un contrôle sécurité si les données ou l’exposition le justifient.

La validation et la relecture sont des étapes séparées du moteur. L’auditeur vérifie une preuve réelle de restauration si elle est requise: une procédure écrite ou un contrôle statique ne suffit pas. Une session neuve du même Qwen apporte une séparation de contexte, pas une famille de raisonnement indépendante.

## Apprendre la logique du métier

Chaque prompt charge l’essentiel de l’accompagnement OPS dans son budget de bootstrap. L’ensemble des rôles doit expliquer, selon le besoin:

- **Pourquoi**: problème, mécanisme, stratégie choisie et compromis.
- **Avant d’agir**: dépendances, permissions, état initial et hypothèses.
- **Comment vérifier**: résultat attendu, mesure ou preuve observable, limite d’un contrôle statique.
- **Comment diagnostiquer**: symptôme, hypothèse, vérification, correction et rollback.

Le guide final progresse de comprendre à utiliser, approfondir et diagnostiquer. Les exercices sont facultatifs, isolés et réversibles; aucun quiz automatique. Une compétence n’est pas déclarée acquise sans pratique vérifiée. Les prompts `AGENTS.md` restent sous 2500 caractères par rôle et les fichiers normalement injectés sous 8000 caractères au total; cela protège le contexte de 8192 tokens sans confondre caractères et tokens.

L’optimisation porte sur **le travail demandé**, pas sur le nombre d’étiquettes: six spécialités ne consomment pas six VRAM. N’appeler que les rôles nécessaires, réutiliser les contributions, couper les documents longs en petites tâches et éviter les générateurs de titres ou un second système RAG. Le gain de vitesse doit être mesuré sur Fedora; conserver six rôles ne supprime pas le coût des tâches et audits réellement lancés.

Source SDK: [outils plugin OpenClaw](https://docs.openclaw.ai/plugins/tool-plugins).
