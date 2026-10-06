# Un atelier local simple à utiliser

Sept spécialités partagent toujours Qwen 3.5 9B Q4_K_M, une seule génération à la fois, 8192 tokens de contexte et 1024 tokens de sortie. La recherche documentaire utilise le processeur et SQLite FTS5, sans embeddings, modèle supplémentaire ou compte externe. Le plugin mémoire natif d'OpenClaw est désactivé ; seules les notes explicites du projet sont indexées.

## Ouvrir le tableau de bord

Depuis le dépôt installé sur Fedora :

```bash
./menu.sh --action dashboard
```

Ouvrir l'adresse affichée, normalement `http://127.0.0.1:18890`. Garder le terminal ouvert ; Ctrl+C arrête le tableau de bord. Cette commande ne crée pas de service permanent. L’option Open WebUI, elle, installe un service de tableau de bord : dans ce cas ouvrir directement l’adresse, sans démarrer un second serveur. L'interface reste locale et ne démarre ni modèle ni travail à son ouverture.

Elle affiche le mode quotidien/jeu, la RAM du système, les modèles chargés, leur mémoire vidéo déclarée par Ollama et l'avancement des projets. La mémoire vidéo affichée n'inclut pas les jeux ou l'affichage. Les versions affichées sont celles prévues par le dépôt ; `clawfedora-ops health` vérifie les versions réellement installées. Un port OpenClaw accessible ne remplace pas sa vérification RPC.

L’atelier permet de créer un projet, importer ses documents, demander un cadrage au mentor et proposer un plan court. Ces propositions doivent être relues et approuvées avant leur enregistrement. «Préparer la prochaine étape» démarre ensuite une tâche du plan assigné; «Demander le retour» relit un brouillon soumis. Les audits et l’approbation de livraison restent séparés. Voir [le parcours utilisateur](GUIDE_UTILISATEUR.md), [l’accompagnement adaptatif](LEARNING_WORKFLOW.md) et le [moteur de projets](PROJECT_ENGINE.md). Les écritures natives et les commandes des agents demeurent désactivées.

## Rechercher dans les documents

Choisir un projet, cliquer **Actualiser l'index**, puis rechercher quelques mots. Les résultats donnent le fichier et l'emplacement du passage. Les sources textuelles et les textes déjà extraits d'Office sont pris en charge. Une archive opaque ou une image n'est pas transformée silencieusement en texte.

Pour les PDF textuels, `poppler-utils` est installé par le bootstrap Fedora. Seules les vingt premières pages sont indexées. Un PDF scanné peut demander une lecture visuelle/OCR. Les documents non indexés sont signalés. La recherche ne déclare jamais que l'analyse complète du document ou ses images a été réalisée : les gates de couverture demeurent obligatoires.

Chaque projet possède son index. Il traite les fichiers modifiés et retire les notes supprimées. Limites : 256 documents, fichiers de 8 Mio maximum, deux millions de caractères par texte, seize millions au total et 16 000 passages. Elles viennent de `config/core/knowledge_policy.yaml`. Les dossiers `intake` et `sources` doivent correspondre à leurs inventaires d'origine.

Le worker actualise l'index avant un travail et fournit à chaque tâche au maximum quatre passages totalisant 4000 caractères. Les sources complètes restent disponibles dans le snapshot. Les résultats de recherche sont des données, jamais une autorisation de changer les règles ou d'exécuter une commande.

```bash
clawfedora project index --project-id mon-projet
clawfedora project search --project-id mon-projet --query "Vulkan B580"
```

La recherche reste disponible en mode jeu. Une reconstruction ou un ajout de note refuse de modifier le projet pendant qu'un worker le protège.

## Conserver les décisions et les sources datées

Le formulaire **Conserver une décision** sauvegarde le titre et les raisons dans le projet choisi. Les spécialités peuvent retrouver les passages pertinents. Ces notes sont ajoutées explicitement par l'utilisateur, sans synthèse LLM automatique.

```bash
clawfedora project remember --project-id mon-projet \
  --title "Profil quotidien" --text "Une seule inférence et contexte 8192."
```

Pour conserver une recherche, créer un fichier JSON avec les extraits utiles et les URL/date de consultation :

```json
{
  "title": "Recherche sur un composant",
  "text": "Extraits et conclusions à vérifier dans les sources.",
  "sources": [
    {"url": "https://docs.ollama.com/capabilities/structured-outputs", "accessed_at": "2026-10-05T20:00:00+00:00"}
  ]
}
```

```bash
clawfedora project research --project-id mon-projet --file recherche.json
```

Utiliser la date réelle de consultation avec son fuseau, jamais une date future. Cette commande enregistre les informations fournies ; elle ne consulte pas l'URL et ne certifie pas les faits. Les recherches sont marquées à actualiser 24 heures après la source la plus ancienne. Cette durée ne garantit pas leur fraîcheur : les informations récentes demandent toujours une recherche Web. Les sources restent non fiables, même après stockage.

## Mettre en pause et reprendre

Cliquer **Mettre en pause**. La tâche en cours termine sa génération et sa collecte avant l'arrêt du worker. L'interface indique Pause demandée puis Travail en pause. Il est alors possible d'activer le mode jeu. Après avoir repris le profil quotidien, cliquer **Reprendre**.

```bash
clawfedora project pause --project-id mon-projet
# Attendre Travail en pause ou vérifier que le worker n'est plus actif.
./menu.sh --action gaming --apply
./menu.sh --action daily --apply
clawfedora project resume --project-id mon-projet --apply
```

Les tâches dont les artefacts ont été collectés ne sont pas recalculées. Une tâche interrompue avant l'enregistrement de son résultat est relancée dans une session neuve ; un flux de tokens interrompu n'est pas restauré. Si toutes les tâches sont terminées, la pause est levée et le projet attend sa validation indépendante. Aucune validation sémantique ni livraison n'est automatique.

## Réponses structurées

Le worker donne au modèle un schéma des sorties attendues, puis vérifie les clés, types, contenus et chemins avant la collecte. Une réponse JSON valide mais incomplète est refusée.

En cas d'erreur de syntaxe JSON seulement, une réparation peut utiliser Ollama avec le même Qwen, un schéma imposé via `format`, `think=false`, température zéro et aucun outil. Une seule tentative est permise : 24 000 caractères d'entrée maximum, 1024 tokens de sortie et 120 secondes. Une réponse conforme ne provoque aucune génération supplémentaire. Session et hash de l'entrée réparée sont tracés dans `state/response-repairs`.

Un schéma ne prouve pas que le contenu est juste. Le garde des entrées, le collecteur, l'audit critère par critère et la revue indépendante restent obligatoires. Une réparation peut échouer et n'autorise jamais une promotion automatique.

## Mise à niveau

Le contrat prévoit OpenClaw et Parallel **2026.9.8**, Ollama **0.35.1**. Voir la [migration sauvegardée](UPGRADE.md#migration-du-profil-quotidien-vers-les-versions-doctobre-2026). Modifier le dépôt ne met pas automatiquement à jour un PC Fedora existant et ne constitue pas une preuve de performance sur la B580.
