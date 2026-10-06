# Profil quotidien adapté à la B580

La cible reste Ryzen 7 7700, 48 Gio de RAM, Arc B580 12 Gio, Fedora 44, `xe` et Mesa/Vulkan. Le dépôt propose désormais six rôles sur **un seul modèle obligatoire**, Qwen 3.5 9B Q4_K_M. Aucun gain en tokens/s, température ou stabilité matérielle n'est annoncé sans mesure sur la machine.

| Limite | Application |
|---|---|
| Un modèle résident | `OLLAMA_MAX_LOADED_MODELS=1`, pas de fallback dans OpenClaw |
| Une inférence par modèle | `OLLAMA_NUM_PARALLEL=1` ; un seul modèle autorisé en production |
| File de quatre requêtes maximum | `OLLAMA_MAX_QUEUE=4`, refus des requêtes supplémentaires |
| Une tâche projet à la fois | Verrou Linux partagé entre tous les projets du runtime |
| Contexte 8192 | Catalogue, options Ollama et modèles exposés à OpenClaw |
| Sortie 1024 tokens | Options de génération et plafond déclaré du modèle |
| Veille du modèle après trois minutes | `keep_alive=3m` |
| Pas de raisonnement long par défaut | `think=false`, `thinkingDefault=off` |
| Recherche concise | Quatre résultats, pages limitées à 4000 caractères |
| Pas de tâches de fond automatiques | Heartbeat désactivé ; lingering facultatif |

Le [tableau de bord et la recherche documentaire](LOCAL_ASSISTANT.md) ajoutent un suivi local, des décisions persistantes, des recherches datées et une pause/reprise entre les tâches. La recherche reste sur le CPU et une réponse conforme ne demande aucune génération supplémentaire.

Les limites Ollama concernent les clients de **ce serveur**. Un autre serveur démarré manuellement ou un candidat llama.cpp consomme aussi le GPU. Ne pas les démarrer simultanément en usage quotidien. Le verrou Python sérialise le worker et ses revues ; les commandes manuelles de modification des projets doivent être exécutées quand le worker est arrêté.

Les sauvegardes utilisent l’API SQLite pour inclure les transactions validées encore dans le journal WAL. Elles restent des instantanés par fichier ; arrêter les écritures et le worker avant une sauvegarde complète garantit la cohérence entre projets et sessions.

## Six spécialités, pas six modèles

- Chef : cadrage, analyse et plan avec dépendances explicites.
- Recherche : faits, sources et actualité via Internet.
- Architecte : architecture, décisions, schémas et documentation.
- DevOps : code proposé, exploitation et préparation des livraisons.
- Sécurité : risques, contrôles et revue, sans exécution système automatique.
- Qualité : validation des critères dans une nouvelle session en lecture.

L'architecte reprend la rédaction technique, le DevOps reprend les releases. Leurs anciens dossiers déjà déployés restent sur disque pour préserver les données ; leurs entrées OpenClaw sont retirées explicitement via le SDK public OpenClaw après application du patch, sans effacer les fichiers. L'auditeur utilise le même modèle mais une session distincte. Cela réduit les échanges et changements de modèle ; cela ne garantit pas une indépendance de raisonnement équivalente à deux familles de modèles.

Le **worker est l'unique ordonnanceur** des projets : le chef prépare le plan et le worker appelle ses spécialistes. Les outils natifs `sessions_spawn`, `sessions_send` et `subagents` sont désactivés. Il n'y a donc pas deux niveaux concurrents de délégation.

## Installation et état sauvegardé

L'installation reste explicite et propose un aperçu avant application :

```bash
./menu.sh --action install
./menu.sh --action install --apply
```

Le bootstrap quotidien évite compilateurs, outils de développement, Podman et KVM. Ils restent disponibles avec `00_bootstrap.sh --with-dev --with-kvm --apply`. Les candidats compilés demandent ces dépendances. Le lingering requiert `10_install_full.sh --apply --enable-linger` ; sans cette option, les services utilisateur suivent la session. Ollama reste un service système.

Les modèles sont stockés dans `models/ollama`, appartenant au compte service Ollama. Le sélecteur Vulkan est dérivé de l'énumération de la **B580**, sans présumer qu'elle est GPU0. Vérifier les logs après activation pour confirmer le périphérique utilisé : un index seul ne constitue pas une qualification.

L'état OpenClaw est regroupé dans `<runtime>/state/openclaw`, avec les versions, digests et preuves dans le runtime. L'installation détecte l'ancien `~/.local/state/openclaw-local`, le copie sans supprimer l'original, vérifie les hashes et crée une sauvegarde. Les sauvegardes incluent l'état du gateway et les configurations générées, excluent les poids et le virtualenv, et sont privées (0600). Le dossier historique reste sensible et ne doit pas être publié.

La restauration exige une destination vide. Après restauration, reprendre la configuration et les définitions systemd pour le nouveau chemin, puis exécuter la santé et les tests d'inférence ; extraire l'archive ne redémarre pas le gateway.

## Exécuter un projet

Les commandes de cadrage et d'ingestion du [moteur de projets](PROJECT_ENGINE.md) restent disponibles. L'analyse, les clarifications et le plan doivent être vérifiés avant d'assigner des tâches. Le worker ne déduit pas automatiquement un plan complet d'une demande ambiguë.

Une fois le projet `ASSIGNED` :

```bash
clawfedora project run --project-id mon-projet
clawfedora project run --project-id mon-projet --apply
clawfedora project review --project-id mon-projet --kind validation --apply
clawfedora project transition --project-id mon-projet --to REVIEW --actor auditeur-qualite --reason validation_pass
clawfedora project review --project-id mon-projet --kind review --apply
clawfedora project package --project-id mon-projet
```

Le worker fournit un snapshot de la tâche et une session neuve. Les entrées et le projet central sont contrôlés par hashes avant la collecte. Prévoir des tâches courtes : 1024 tokens de sortie ne permettent pas de produire plusieurs longs fichiers dans une seule réponse. Les justifications de chaque critère, les hashes du snapshot et la session de revue sont conservés dans le verdict. Le modèle répond en JSON avec les contenus des fichiers ; le collecteur accepte uniquement les chemins attendus, les scopes du rôle et le namespace de la tâche. Les fichiers vides, trop volumineux, liés ou sortant du projet sont refusés. Un PASS de tâche signifie **artefacts collectés** ; le projet doit ensuite passer validation et revue. Une erreur de génération reste une tentative FAIL traçable, sans promotion automatique.

Les agents ont `read`, les outils documents et les outils web utiles. Les écritures natives, `exec` et `process` sont désactivés. `workspaceOnly` n'est pas présenté comme un sandbox de commandes. Le profil quotidien propose du code et des scripts ; leur exécution sur l'hôte reste une action opérateur. Un futur profil d'exécution isolée devra être qualifié avant activation.

Les documents joints et résultats web sont des données non fiables. Les permissions du modèle ne changent jamais sur instruction provenant d'un document.

## Jouer et reprendre l'IA

```bash
scripts/linux/21_daily_profile.sh gaming
scripts/linux/21_daily_profile.sh gaming --apply
scripts/linux/21_daily_profile.sh daily --apply
```

Le mode jeux refuse d'interrompre un worker actif, bloque les nouveaux workers, arrête le gateway, le candidat llama.cpp et Ollama pour libérer le GPU. Il affecte les autres clients du même serveur Ollama. La reprise remet en route Ollama et le gateway. Le profil énergétique du PC n'est pas modifié.

## Santé et identité du modèle

```bash
clawfedora-ops health
clawfedora-ops health --probe
```

La santé vérifie les versions exactes, l'inventaire JSON sans troncature, les hashes adoptés, le gateway RPC, SELinux, firewalld, la B580/Vulkan et les limites effectives du service. `--probe` ajoute une génération courte et vérifie que de la VRAM est utilisée. Cela ne mesure ni la stabilité prolongée, ni un offload complet, ni les performances.

`models-lock --apply` adopte explicitement le SHA-256 et la quantification observés ; son état reste **PENDING**. Une adoption ne vaut pas qualification. Si un tag déjà adopté change, le contrôle refuse la nouvelle identité. Pour une mise à jour : sauvegarder l'ancien verrou, comparer les identités, requalifier puis adopter explicitement le nouveau fichier. Ne pas supprimer le verrou pour masquer une dérive.

## Expérimentations séparées

Gemma, Ministral et Granite n'interviennent pas dans le routage quotidien. Le profil HARD-40M conserve ses trois modèles, 30 cas, seuils et comparaisons 8K/16K. Préparer cette expérience explicitement :

```bash
clawfedora-ops models --experimental
clawfedora-ops models --experimental --apply
clawfedora-ops models-lock --experimental --apply
```

Ces commandes n'activent pas ces modèles dans OpenClaw. Le benchmark direct les charge successivement. Une promotion de modèle/backend ou de 16K doit modifier explicitement les contrats après preuves réelles. Les tests de contexte long exigent des valeurs retrouvées au début, au milieu et à la fin, ainsi qu'un nombre de tokens d'entrée effectivement traité. Les simples noms de clés ou une réponse non vide ne suffisent plus.

La mesure VRAM expérimentale utilise les clients DRM `xe` de la B580 sélectionnée et échantillonne pendant l'inférence. Un compteur d'un iGPU AMD ne peut pas être utilisé à sa place. Si les `fdinfo` du compte Ollama sont inaccessibles, la comparaison est bloquée : il faut organiser une collecte autorisée sur Fedora, sans annoncer un pic fictif. Ces compteurs mesurent les allocations des clients observables, pas toute la mémoire physique occupée par les firmwares.

`clawfedora-golden` sans `--live` vérifie le moteur avec des sorties synthétiques. Ce résultat ne peut plus autoriser L8. `clawfedora-golden --live` appelle le worker puis l'auditeur réel pour les cinq scénarios et le projet représentatif ; le gate humain final reste obligatoire. Le script `scripts/validation/check_openclaw_schema.py` valide aussi les deux providers et la migration avec le CLI OpenClaw exact ; il vérifie le rejet de l’ancien paramètre PDF. Ce contrôle natif demande le runtime et le plugin épinglés, et reste distinct de la CI existante.
