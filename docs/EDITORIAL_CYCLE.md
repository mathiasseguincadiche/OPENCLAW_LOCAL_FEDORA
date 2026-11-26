# Boucle d'excellence éditoriale

[Charte Premium](EDITORIAL_PREMIUM_V2.md) · [Studio graphique](GRAPHIC_STUDIO.md)

Le worker peut exécuter une révision éditoriale intermédiaire avant de
collecter une source Markdown. L'audit final indépendant et la validation
humaine restent obligatoires ; aucun accès de publication n'est ajouté.

## Activation dans le plan approuvé

Dans une tâche du rédacteur pédagogique, ajouter un critère de contenu
commençant par `[revue éditoriale]`. Exemple :

~~~json
{
  "id": "guide-service",
  "role": "redacteur-pedagogique",
  "title": "Guide du service",
  "objective": "Expliquer le mécanisme et les limites",
  "depends_on": [],
  "expected_outputs": ["deliverables/guide-service/guide.md"],
  "acceptance_criteria": ["[revue éditoriale] Expliquer les choix et leurs limites"],
  "learning_mode": "direct"
}
~~~

Pour un vrai projet, conserver les dépendances techniques du plan.
Portée initiale : une source Markdown, 12 000 octets maximum, mode direct,
route locale, sans critère de preuve machine ni export dans cette tâche.
Le mode guidé ne déclenche pas la boucle : l'exercice de l'apprenant
reste prioritaire. Les autres tâches et les plans anciens sont inchangés.

## Fonctionnement

1. Le rédacteur produit un brouillon dans son espace protégé.
2. Le worker contrôle les chemins et la structure Markdown.
3. L'auditeur reçoit la version exacte, le contrat et les sources autorisées
   dans une nouvelle session et un snapshot en lecture seule, sans résumé
   d'autocertification du rédacteur.
4. Sept critères doivent être examinés : exactitude, rédaction, structure,
   pédagogie, préservation, sécurité et preuves. Chaque constat cite
   un extrait exact et donne une justification et une action.
5. En cas de défaut, le rédacteur corrige dans une nouvelle session.
   Deux corrections maximum, trois audits maximum ; un contenu identique
   ou cyclique arrête la boucle. Aucun brouillon rejeté n'est collecté.
6. Un résultat intermédiaire favorable permet la collecte ordinaire.
   Les preuves d'outils de la dernière version seules sont collectées.
   La validation et la revue finales suivent le workflow habituel.

Un reçu `evidence/<tâche>/editorial-cycle-<session>.json` contient les
empreintes SHA-256 des versions, sessions et états des critères ; aucun
extrait ni secret ne doit y être recopié. Il distingue
MODEL_REVIEW_PASSED, NO_PROGRESS et REVISION_LIMIT. Une réponse
structurée invalide interrompt aussi la tâche, sans reçu favorable.

## Limites

Deux sessions avec le même modèle ne garantissent pas l'indépendance de
raisonnement. Un extrait présent n'établit pas l'exactitude d'un constat.
Le résultat ne certifie ni rendu Notion/GitHub, ni preuve d'exécution, ni
compétence. La revue native desktop clair/sombre/mobile et l'approbation
de publication demeurent distinctes. Les tests CI simulent les agents ;
la qualification des modèles sur Fedora reste à réaliser.

Les SVG, Draw.io, sources JSON Notion, rapports multi-fichiers et mises
à jour de wiki ne sont pas inclus dans cette première boucle.
