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

Pour une notion publique complexe, une longue analyse ou une tâche agentique, le modèle « · cloud (DeepSeek) » peut apporter plus de capacité que Qwen 9B. Ce n'est pas une preuve qu'il enseigne toujours mieux : compare les deux sur tes propres questions. Garde « · local » pour tout ce qui touche ton travail, tes données confidentielles ou ce dont tu n'es pas sûr. Les consignes du mentor sont les mêmes dans les deux modes. Voir [Discuter](03-discuter.md) et [Le cloud, facultatif](12-cloud.md). Un bon réflexe d'apprentissage reste le même quel que soit le modèle : vérifier une version, une commande ou un chiffre dans la documentation officielle.

## Obtenir des explications fiables

Un modèle de 9 milliards de paramètres peut se tromper avec assurance. Le mentor est cadré pour limiter cela, et tu as des moyens de le vérifier.

Ce que les consignes du mentor lui imposent :
- distinguer ce qui est **observé**, **vérifié**, **proposé** et **non vérifié**, au lieu de tout présenter au même niveau de certitude ;
- dire la portée exacte d'un contrôle : `terraform validate` ne vérifie que la cohérence interne (pas un `plan` ni un `apply`), un lint n'est ni un test ni un déploiement, l'idempotence Ansible se prouve par deux exécutions ;
- ne citer que des sources réellement renvoyées par un outil de recherche, avec leur date, et jamais une URL inventée ;
- ne jamais recopier un secret.

Ce que tu peux faire :
1. Pour une version, une commande sensible ou un chiffre, demande « avec quelle source ? » : le mentor cherche, ou dit qu'il ne sait pas.
2. Demande-lui « qu'est-ce qui n'est pas vérifié dans ta réponse ? ».
3. Vérifie toujours dans la documentation officielle avant d'exécuter.
4. Pour **une notion publique complexe ou une tâche longue**, essaie le modèle « · cloud (DeepSeek) ». Les benchmarks publics indiquent une forte capacité agentique et de code, mais pas une supériorité pédagogique démontrée face à Qwen 3.5 9B. Garde « · local » pour le travail et le confidentiel. Voir [Quel modèle pour expliquer](../DECISION_MODELE.md) et [Le cloud, facultatif](12-cloud.md). Compare sur tes propres questions : c'est cette mesure qui tranchera pour ton usage.

La qualité réelle des explications n'a pas encore été mesurée sur ta machine : voir [STATUS](../../STATUS.md).

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
