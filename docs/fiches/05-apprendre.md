# Apprendre

[← Guide](../GUIDE.md)

Recevoir une réponse claire aide à comprendre. Cela ne suffit pas pour savoir faire. L'atelier t'explique d'abord, sans imposer d'exercice. Si tu choisis de pratiquer, il te laisse agir puis relit ton travail.

## Le mentor

Le Mentor infrastructure/OPS est ton interlocuteur par défaut. Il part de ce que tu sais déjà, Linux et le réseau, pour relier une notion nouvelle à quelque chose de familier : un service, un port, un processus, un droit. Il ne refait pas un cours sur ce que tu maîtrises.

Ce que tu peux lui demander dans le chat :

| Ton besoin | Ce qu'il fait |
|---|---|
| Comprendre | Une réponse directe et un petit exemple |
| Te débloquer | Une hypothèse et une vérification à faire |
| Pratiquer | Une petite étape, puis des indices si tu bloques |
| Documenter | Une structure adaptée à ton document |

Une bonne façon de l'utiliser : demande un indice plutôt que la solution, partage ton essai, puis demande une correction.

## Apprendre avec le cloud, si tu l'as activé

Pour comprendre une notion publique, le modèle « · cloud (GLM) » du chat peut mieux expliquer que Qwen. Choisis-le pour des questions sans secret ; garde « · local » pour tout ce qui touche ton travail ou ce dont tu n'es pas sûr. Les consignes du mentor sont les mêmes dans les deux modes. Voir [Discuter](03-discuter.md) et [Le cloud, facultatif](12-cloud.md). Un bon réflexe d'apprentissage reste le même quel que soit le modèle : vérifier une version, une commande ou un chiffre dans la documentation officielle.

## Guidé ou direct

Par défaut, les nouveaux projets sont en mode **direct** : tu reçois l'explication ou la proposition complète, sans exercice bloquant. Le mode guidé est un choix. Les contrats déjà approuvés des anciens projets sont préservés.

Dans un projet, chaque tâche suit l'un de ces modes :

| Mode | Ce qui se passe | Quand |
|---|---|---|
| **Guidé** | Le rôle explique un exemple, te donne une amorce à compléter, puis relit ton travail | Tu découvres une compétence |
| **Direct** | Le rôle propose le résultat complet | Tu maîtrises le sujet, ou c'est une recherche ou une rédaction |
| **Adaptatif** | Aide directe par défaut ; exercice guidé uniquement si tu le sélectionnes pour cette tâche | Si tu veux choisir étape par étape |

## La boucle de pratique

1. **Comprendre.** Le rôle explique le mécanisme sur un exemple différent de ton exercice.
2. **Faire.** Tu complètes les fichiers. Avant d'exécuter, tu prévois ce qui devrait se passer.
3. **Décrire.** Tu indiques ton raisonnement et ce que tu as observé, y compris ce que tu n'as pas testé.
4. **Faire relire.** Tu soumets, puis tu demandes le retour. Le rôle relit le travail réellement soumis.
5. **Corriger ou continuer.** Un critère manquant donne `REVISE` : tu corriges et tu resoumets. Sinon tu passes à la suite, avec moins d'indices.

Tant que ton travail n'est pas relu, les tâches suivantes attendent.

## Tes notes de suivi

Dans un projet, « Mon accompagnement et la continuité du chat » contient cinq notes courtes : tes acquis, ton sujet, ta difficulté, tes observations, ta prochaine étape. Tu les écris toi-même ; aucun modèle ne les modifie. Le mentor les reçoit pour reprendre là où tu en étais.

## Relier les outils au métier

Un outil s'apprend plus vite quand on sait à quel besoin il répond.

| Besoin | Outil | Réflexe à exercer |
|---|---|---|
| Versionner un changement | Git | petit changement lisible, historique, retour arrière |
| Vérifier avant de livrer | CI | critères, échec visible, aucun secret en clair |
| Construire une unité déployable | Docker | distinguer image, conteneur, volume, réseau |
| Décrire des ressources | Terraform | état, dépendances, lire le plan avant d'appliquer |
| Configurer des systèmes | Ansible | idempotence, inventaire, vérification |
| Exploiter des applications | Kubernetes | état désiré, sondes, ressources, diagnostic |
| Comprendre un incident | journaux, métriques | observation → hypothèse → test → correction |

Tu n'as pas besoin de tout pour un premier exercice. Commence par un service Linux que tu sais observer, mets-le dans un dépôt avec un contrôle automatique, puis conteneurise. Ajoute le reste quand un besoin concret le justifie.

## Ce que l'atelier ne fait pas

- Il n'exécute pas tes scripts et ne déploie rien : tu le fais dans ton laboratoire ou ta CI.
- Il ne certifie aucune compétence. Un retour positif signifie que les critères ont été relus sur ce que tu as soumis.
- Il ne remplace pas les outils imposés par ta formation : il t'aide à les aborder dans le bon ordre.
