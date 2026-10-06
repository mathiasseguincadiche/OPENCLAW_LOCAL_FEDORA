# Apprendre le DevOps infrastructure/OPS en construisant

L’objectif est de devenir capable de choisir une stratégie, expliquer son mécanisme, produire son travail et vérifier le résultat. Une réponse claire aide à apprendre; elle ne remplace pas la pratique. Le dépôt propose un accompagnement local, pas une certification de compétence ni une promesse de qualité égale à un service cloud.

## Un parcours proportionné

À la création d’un projet dans l’atelier, choisir **Guidé** et, si utile, indiquer jusqu’à trois objectifs. Le chef cadre un projet court avec les spécialistes nécessaires. Chaque étape suit cette logique:

1. Le spécialiste expose le problème et un mécanisme, définit les mots utiles et montre un petit exemple distinct de l’exercice.
2. Il prépare une amorce avec des éléments à compléter. Le moteur conserve cette proposition en attente: aucune sortie finale n’est publiée et les dépendants ne démarrent pas.
3. L’apprenant complète ses fichiers, décrit son raisonnement et indique ses observations ou ce qu’il n’a pas exécuté. Le formulaire n’exécute aucun code.
4. La soumission passe par le collecteur et devient une contribution du projet. Ce PASS signifie «artefacts collectés», pas «fonctionne en production» ni «compétence acquise».
5. L’utilisateur prépare l’étape suivante. Après toutes les contributions, validation et relecture examinent les critères, les sources et la qualité des explications. La livraison reste explicitement approuvée par l’utilisateur.

Les éléments d’une réponse trop longue sont découpés en étapes; contexte 8K et sortie 1024 tokens restent inchangés. Un contrat compact `context/learning/contract.json` accompagne cadrage, plan, tâches et audits. Le contrat commun est réellement ajouté au `AGENTS.md` de chaque workspace, pas seulement déposé dans un fichier séparé.

Dans une discussion Open WebUI, les mêmes consignes pédagogiques s’appliquent, mais aucun jalon de projet n’est créé automatiquement. Demander un indice, partager son essai puis demander une correction est une bonne utilisation du chat. Les comportements rédactionnels du Qwen réel restent à évaluer sur la machine: un prompt n’est pas une preuve de qualité.

## Relier les outils au métier

Les produits s’apprennent plus facilement lorsqu’on sait quelle responsabilité ils remplissent:

| Besoin | Exemple d’outil | Réflexe à exercer |
|---|---|---|
| Versionner le changement | Git | petit diff compréhensible, historique et retour arrière |
| Vérifier avant de livrer | CI | critères, échec visible, preuves; aucune clé en clair |
| Construire une unité déployable | Docker | distinguer image, conteneur, volume et réseau |
| Décrire les ressources | Terraform/OpenTofu | état, dépendances, plan et coût avant un apply |
| Configurer les systèmes | Ansible | idempotence, inventaire et vérification |
| Exploiter les applications | Kubernetes | état désiré, sonde, ressources et diagnostic |
| Comprendre un incident | journaux/métriques | observation → hypothèse → test → correction → vérification |

Cela ne rend pas tous ces outils nécessaires au premier exercice. Commencer par un service Linux observable, puis son dépôt et un contrôle CI; conteneuriser ensuite. Ajouter provisionnement, configuration et orchestration quand un besoin concret le justifie. AWS/Azure se choisit pour un exercice précis, avec budget et droits définis, pas comme dépendance de l’IA locale.

## Spécialistes et rédacteur

Chaque spécialiste enseigne dans son domaine. L’architecte conçoit les flux, limites et schémas et justifie ses décisions. Le DevOps explique les effets et les vérifications. La sécurité fait comprendre scénarios et contrôles. La recherche date ses sources. Le chef ordonne les petites étapes. L’auditeur vérifie la fidélité et les preuves.

Le **rédacteur pédagogique** organise les contributions actuelles, relie les notions, définit le vocabulaire et conserve les nuances. Il ne décide pas silencieusement de l’architecture et ne résout pas les étapes pratiques en attente. Le moteur refuse une tâche de rédaction qui ne dépend pas, directement ou indirectement, de toutes les contributions techniques du plan. Une modification technique entraîne donc aussi la reprise de sa synthèse. Sept rôles restent sept profils du même modèle: le coût vient des appels réellement effectués. Une tâche simple peut n’utiliser qu’un spécialiste.

## Reprendre une modification sans incohérences

Dans un projet exécuté, ouvrir «Demander une modification cohérente», choisir la contribution et expliquer le changement. Le bouton de prévisualisation montre la tâche et tous ses dépendants transitifs. Après approbation:

- le moteur archive leurs livrables, preuves, propositions guidées et bundles dans `history/revisions/revision-NNN`;
- il garde les contributions non affectées et leurs bundles actuels;
- les tâches concernées deviennent PENDING, les audits/package précédents quittent l’état actif et le projet revient IN_PROGRESS;
- les nouvelles étapes reçoivent le motif approuvé et les contributions à jour; le rédacteur est repris s’il dépend de la contribution modifiée;
- validation, relecture, packaging et livraison doivent être renouvelés.

Les numéros de tentatives continuent d’augmenter pour ne pas écraser les anciens bundles. Le budget de deux tentatives s’applique à chaque reprise approuvée. Les sources initiales restent protégées. Ce mécanisme suit les **dépendances du plan**, pas une compréhension automatique de tout lien sémantique: le chef et l’utilisateur doivent relier les tâches correctement. Si le périmètre, les sources ou les dépendances changent profondément, créer un nouveau projet cadré plutôt que détourner cette reprise.

## Choisir une réponse directe

Le mode **Direct** autorise une proposition complète lorsque l’utilisateur le choisit à la création. Il conserve les explications utiles et les audits, mais ne crée pas de jalon de pratique. Les projets déjà approuvés sans contrat d’apprentissage conservent leur comportement, sans ajouter de nouvelles obligations à leur plan. Les Golden Projects de qualification choisissent explicitement Direct: ils vérifient le moteur et ne représentent pas une formation achevée.

Aucun score automatique, quiz permanent, agenda de révision ou matrice de compétences n’est ajouté. Les soumissions restent des déclarations humaines; une preuve de restauration ou de déploiement doit provenir de l’exercice réel. La qualité technique et l’apprentissage ne sont jamais déduits l’un de l’autre.
