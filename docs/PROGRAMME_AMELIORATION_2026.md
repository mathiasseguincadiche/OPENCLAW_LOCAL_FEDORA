# Programme d'amélioration validé — Atelier IA hybride Fedora

> **Archive de conception 2026 — non normative.** Ce document conserve les décisions et audits historiques. Ses anciennes versions, procédures et priorités ne décrivent pas nécessairement le socle courant. Consulter [l'état actuel](../STATUS.md), le [sommaire des archives](archives/2026/README.md) et [l'installation Fedora 45](INSTALLATION_SIMPLE_FEDORA45.md) avant toute commande.


> **Mise à jour des versions, 18 octobre 2026 :** cible d'installation neuve OpenClaw 2026.10.4, Ollama 0.40.6 et Open WebUI 0.12.3-slim, sous réserve des tests d'intégration et de réception Fedora. Les références antérieures à 2026.10.3/0.40.4/0.12.1 sont historiques.


[← README](../README.md) · [État mesuré](../STATUS.md) · [Stratégie hybride](ARCHITECTURE_HYBRIDE.md)

**Architecture non négociable : Fedora est l'hôte natif d'OpenClaw, Ollama,
des agents, de la passerelle et du moteur de projets. Open WebUI tourne
dans un conteneur Podman rootless sur Fedora ; DeepSeek est distant via
OpenRouter uniquement sur autorisation. Aucune VM Rocky Linux ni image
Rocky n'est nécessaire au fonctionnement de l'atelier.** La VM Rocky de
formation DevOps est un projet externe facultatif, à ne pas confondre avec
l'infrastructure IA.

**Date de cadrage : 12 octobre 2026.** Cible : un atelier hybride **Qwen local + DeepSeek cloud**, sept rôles DevOps spécialisés, une interface Web cohérente, un moteur de projet sûr, une pédagogie accessible, des résultats **vérifiables**, et **25 €/mois maximum** de budget API.

## État des travaux de finition — 14 octobre 2026

Les changements [#110](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/110)
à [#114](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/pull/114)
sont **intégrés et contrôlés automatiquement** : cohérence du bootstrap Python/npm,
isolation du canary WebUI, destination cloud non redirigeable, comparaison
hors ligne des évaluations humaines des sept rôles, précontrôle de services
actifs/activés au démarrage. La CI ne prouve pas les essais machine.

Les objectifs encore ouverts nécessitent soit un verrouillage cryptographique
intégral des dépendances transitives, soit la phase **finale d'acceptation**
déjà documentée (Fedora 45 Workstation / GNOME 51, Intel B580, navigateur et SQLite WebUI 0.12,
véritable fournisseur OpenRouter avec prix/effort, restauration et performance
des modèles). Ne pas changer le pin de production WebUI, le routage cloud
ou le plafond de 25 €/mois sur la seule base de ces tests.

## Cible définitive de première installation

Le projet est préparé pour **Fedora 45 Workstation / GNOME 51 sous Wayland**,
avec l'installation de OpenClaw, Ollama et Open WebUI directement sur cette
base neuve. Les scripts n'acceptent plus Fedora 44. À la date du
14 octobre 2026, la sortie stable est seulement programmée au
20 octobre (éventuel report) : les essais sur conteneur Fedora 45
restent des prétests et la réception physique suit la publication finale.

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
| **W1 : Open WebUI 0.12.1** | Première installation directe, sans migration de 0.11.4 | PR #117 : le tag stable 0.12.1-slim est résolu en digest immuable par Podman pour systemd ; canary #94/#111 facultatif | Qualifier véritablement navigateur, fichiers, Functions, voix et sqlite sous Fedora |
| **W2 : vrai streaming** | Réponse affichée pendant l'inférence avec annulation fiable | **PR #89 et #90 fusionnées** : transport SSE strict et pont WebUI raccordé en canary privé **désactivé par défaut**, avec prévalidation CLI, verrou partagé et jeton opérateur côté serveur ; cloud/projets exclus du canary | Tester sur Fedora la réception progressive, l'annulation, le verrou et le rollback sans laisser le Gateway privilégié actif |
| **W3 : commandes visuelles** | Gérer projet, approbation, audit, livraison dans l'UI | Actions déterministes et confirmations serveur ; PR #96 : **six boutons de lecture seule**, dont inventaire des sources et indication d'intégrité ; autres transitions contrôlées | Tester les dialogues réels et un parcours de projet complet dans Open WebUI |
| **F1 : livrables professionnels** | PDF/DOCX/Draw.io cohérents, gros documents par sections | PR #93 : assembleur humain de 16 sections Markdown, exports PDF/DOCX et manifeste SHA-256 ; PR #98 : **Draw.io natif multi-vues fusionné** (jusqu’à 8 pages) | Inspection visuelle du rendu PDF/DOCX et des pages Draw.io dans l'éditeur |
| **K1 : contexte de projet** | Meilleure recherche des sources et décisions | PR #95 : sources contrôlées contre l'inventaire ; citations FTS périmées exclues, page et ligne conservées si présentes | Comparer la recherche réelle sur des corpus et contrôler les omissions |
| **I1 : forges et preuves** | Lire les vrais runs GitHub/GitLab en lecture seule | PR #92 : statut global et SHA vérifiés, option `--jobs` pour les métadonnées publiques non paginées ; connecteurs privés, logs/artefacts et dépôt de preuves non développés | Vérifier les API publiques réelles, la limitation de débit et les droits des futurs connecteurs |
| **O1 : exploitation** | Suivi santé, sauvegardes, consommation VRAM/ressources, alertes utiles | Indicateurs pertinents, lecture seule, pas de télémétrie inutile | Vérifier veille, relance, sauvegarde et restauration |
| **R1 : qualification finale** | Démontrer fiabilité et utilité sur Fedora/B580 + OpenRouter | **N/A** : seule la phase de réception peut attester ce niveau | Rapports datés, scénarios utilisateur et limites résiduelles |

**Les lots ne sont pas tous terminés parce qu'ils figurent dans cette table.** L'état exact doit être tenu dans `STATUS.md` et les PR GitHub ; ne pas utiliser une note « 10/10 » avant des mesures reproductibles.

## Ordre de travail recommandé

1. **Streaming canary prêt en code** (PR #90) : vérifier la configuration réelle du Gateway et réserver les essais de fragments/annulation/rollback à la phase finale Fedora.
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
