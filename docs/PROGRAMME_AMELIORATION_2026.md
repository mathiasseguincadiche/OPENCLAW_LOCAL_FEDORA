# Programme d'amélioration validé — Atelier IA hybride Fedora

[← README](../README.md) · [État mesuré](../STATUS.md) · [Stratégie hybride](ARCHITECTURE_HYBRIDE.md)

**Architecture non négociable : Fedora est l'hôte natif d'OpenClaw, Ollama,
des agents, de la passerelle et du moteur de projets. Open WebUI tourne
dans un conteneur Podman rootless sur Fedora ; DeepSeek est distant via
OpenRouter uniquement sur autorisation. Aucune VM Rocky Linux ni image
Rocky n'est nécessaire au fonctionnement de l'atelier.** La VM Rocky de
formation DevOps est un projet externe facultatif, à ne pas confondre avec
l'infrastructure IA.

**Date de cadrage : 12 octobre 2026.** Cible : un atelier hybride **Qwen local + DeepSeek cloud**, sept rôles DevOps spécialisés, une interface Web cohérente, un moteur de projet sûr, une pédagogie accessible, des résultats **vérifiables**, et **25 €/mois maximum** de budget API.

## Le principe : préparer le code, qualifier en dernier

On produit les changements **par PR de petite taille** ; une CI de non-régression valide le code au fur et à mesure. Les **tests de réception réels** (Fedora/B580, conteneur Open WebUI, vrai OpenRouter, microphone, performances, restauration) forment **la dernière phase**, une fois les composants stabilisés.

Une CI verte ne prouve ni un vrai navigateur opérationnel, ni un coût fournisseur correct, ni la qualité d'un raisonnement. Chaque statut doit être explicite :
- **À faire** : pas encore développé ;
- **En préparation** : branche / PR ouverte ;
- **Intégré au code** : fusionné, tests automatisés satisfaits ;
- **Qualifié réel** : essais matériels et services externes réussis, preuves datées.

## Lots de travail et critères d'acceptation

| Lot | Objectif | Critère pour dire « intégré au code » | Phase de réception finale |
|---|---|---|---|
| **S0 : confidentialité des sessions** | Isoler les historiques et désactiver les communications inter-agents inutiles | Configuration explicite `tools.sessions.visibility=self`, `tools.agentToAgent.enabled=false`, test contrat | Vérifier qu'aucun rôle ne voit les sessions des autres |
| **D1 : validateur DevOps indépendant et facultatif** | Proposer des contrôles statiques hors ligne, sur demande humaine, sans shell aux agents | CLI `clawfedora-lab` isolée : aucun prérequis Rocky pour OpenClaw ; image OCI de validateurs au choix, épinglée et contrôlée | Si l'utilisateur choisit cet outil, qualifier séparément l'image et les vrais validateurs Podman |
| **Q1 : évaluations des sept agents** | Mesurer rigueur, pédagogie, preuves et sécurité | Suite synthétique par rôle, schéma de revue humaine et agrégateur qui refuse les notes incomplètes | Mesurer Qwen vs DeepSeek sur les mêmes cas et examiner les fichiers générés |
| **Q2 : prompts adaptés au modèle** | Réduire répétitions, ajuster contraintes de contexte et méthode par rôle | Prompts sous limites OpenClaw, tests de structure et jeux de régression | Mesurer l'amélioration réelle sans dégrader le local |
| **C1 : cloud efficient** | Profils Rapide/Équilibré/Approfondi, coûts et visibilité | Profils contrôlés localement, avec `--apply`, verrou worker, effort et plafonds bornés ; **le profil reste global**, les profils par tâche et l'ajustement automatique ne sont pas livrés | Mesurer latence, coût, qualité sur OpenRouter réel |
| **C2 : routage assisté** | Recommander Qwen/DeepSeek sur critères explicables | Premier niveau : `!modele` et bouton WebUI, conseil statique **sans accès à l'historique** ; route toujours manuelle. Évaluation par tâche/projet : non développée | Vérifier pertinence, refus sensibles, budget |
| **W1 : Open WebUI 0.12** | Migration isolée et interface moderne | Image par digest, canary DB, filtres et fonctions configurés, restauration prévue | Valider vraie base, filtres, fichiers, voix, navigateur |
| **W2 : vrai streaming** | Réponse affichée pendant l'inférence avec annulation fiable | **Transport SSE serveur à serveur préparé** avec décodage incrémental et refus ; **pont WebUI non raccordé**, jeton opérateur non exposé et activation suspendue aux vérifications du worker/verrou/budget | Mesurer premier token avant fin de réponse, arrêt propre |
| **W3 : commandes visuelles** | Gérer projet, approbation, audit, livraison dans l'UI | Boutons reliés au pont déterministe, confirmation serveur, test d'autorisation | Parcours complet sans mémoriser de commandes |
| **F1 : livrables professionnels** | PDF/DOCX/Draw.io cohérents, gros documents par sections | Rendu et assemblage déterministes, sources éditables, pas de troncature silencieuse | Inspection visuelle d'exemples représentatifs |
| **K1 : contexte de projet** | Meilleure recherche des sources et décisions | Index vérifiable, couverture par document, références de fichiers non fabriquées | Comparer recherche actuelle et améliorée sur des corpus réels |
| **I1 : forges et preuves** | Lire les vrais runs GitHub/GitLab en lecture seule | CLI publique `clawfedora-ci-proof` : statut global et SHA vérifiables ; connecteurs privés, jobs détaillés et stockage contrôlé des preuves encore à développer | Vérifier API réelles, journaux CI et audit de permissions |
| **O1 : exploitation** | Suivi santé, sauvegardes, consommation VRAM/ressources, alertes utiles | Indicateurs pertinents, lecture seule, pas de télémétrie inutile | Vérifier veille, relance, sauvegarde et restauration |
| **R1 : qualification finale** | Démontrer fiabilité et utilité sur Fedora/B580 + OpenRouter | **N/A** : seule la phase de réception peut attester ce niveau | Rapports datés, scénarios utilisateur et limites résiduelles |

**Les lots ne sont pas tous terminés parce qu'ils figurent dans cette table.** L'état exact doit être tenu dans `STATUS.md` et les PR GitHub ; ne pas utiliser une note « 10/10 » avant des mesures reproductibles.

## Ordre de travail recommandé

1. **Streaming réel Open WebUI sur Fedora** : réponses progressives, gestion des annulations, conservation du verrou et du budget cloud, refus vérifiés.
2. **Pilotage visuel des projets** : créer, sélectionner, cadrer, approuver, lancer, auditer et livrer via des commandes serveur déterministes et confirmations humaines.
3. **Compatibilité Open WebUI et ergonomie** : canary 0.12, fonctions, téléchargements, pièces jointes, meilleure navigation et contrôle des permissions.
4. **Fiabilité du système hybride** : prompts, recherche locale, exports, régressions, contrats et dépenses vérifiables.
5. **Réception finale sur Fedora** : B580, OpenClaw/Ollama, Open WebUI/Podman, DeepSeek/OpenRouter, sauvegarde/restauration et qualité des agents.
6. **Option hors cœur IA uniquement si utile** : qualification de `clawfedora-lab` avec une image de validateurs OCI au choix. Aucune obligation Rocky Linux.

## Critères de décision sur chaque amélioration

- **Sûr :** aucune sortie cloud non autorisée, aucun shell libre, originaux immuables.
- **Vrai :** une proposition, un lint, une CI et un déploiement ne sont jamais confondus.
- **Utile :** chaque fonction sert une activité DevOps/Infra-Ops réelle ou facilite l'apprentissage.
- **Pédagogique :** fichiers utilisables et explications compréhensibles sans devoir faire un quiz.
- **Économe :** capacité DeepSeek réservée aux tâches qui le justifient, dépenses réconciliées.
- **Maintenable :** versions épinglées, PR ciblées, documentation et tests de régression.

**Cible : un excellent assistant de travail et mentor DevOps, pas une usine à agents difficile à maintenir.**
