# Interface de l'atelier — design system InfraOps Studio

[← Documentation](README.md) · [Réception visuelle](validation/VISUAL_RECEPTION_NATIVE.md) · [Notion](NOTION_DASHBOARD.md) · [GitHub](GITHUB_CHAT_DASHBOARD.md)

## Périmètre

Le design system commun modernise les **trois pages de l'atelier local** :

- `http://127.0.0.1:18890/` : vue d'ensemble, ressources, projets et espace documentaire ;
- `http://127.0.0.1:18890/github.html` : publication GitHub sous approbation ;
- `http://127.0.0.1:18890/notion.html` : préparation et revue Notion sous approbation.

Il ne remplace **pas** l'application Open WebUI de discussion
(`http://127.0.0.1:3000`), dont le thème, la navigation et les composants
sont gérés par le logiciel tiers.

## Principes d'expérience retenus

**Un espace de travail, pas une succession de formulaires.**

1. **Navigation permanente :** rail pour Projets, GitHub et Notion avec
   indication de l'espace actif. Sur mobile, ce rail devient une barre
   horizontale compacte.
2. **Hiérarchie visuelle :** en-tête lisible, cartes sobres, typographie
   système soignée, indicateurs de ressources séparés et actions primaires
   reconnaissables.
3. **Divulgation progressive :** les processus GitHub et Notion sont
   distribués en onglets clairs ; une seule activité majeure est
   affichée à la fois. Les formulaires d'approbation ne s'affichent
   qu'après obtention d'un plan valide, comme auparavant.
4. **États et erreurs :** messages, aperçus, diffs et validations restent
   lisibles et distincts. Les permissions du serveur ne changent pas.
5. **Accessibilité :** onglets `role=tablist` / `role=tab`, `aria-selected`,
   navigation clavier avec flèches, Début/Fin, raccourcis natifs,
   contours de focus, `[hidden]` respecté, mouvement réduit.
6. **Adaptation et thèmes :** bureau, tablette et mobile ; thème clair
   ou sombre activable, préférence conservée seulement dans le navigateur.
   Aucune police, image, feuille de style ou script n'est chargé sur un CDN.

Le code commun se trouve dans `src/clawfedora/web/workbench.css` et
`workbench.js`. Ce dernier **n'appelle pas les API réseau** : il ne fait
qu'améliorer la présentation. Les contrôleurs existants
`dashboard.js`, `github.js`, `notion.js`, `notion-rich.js` et
`notion-media.js` gardent la responsabilité des opérations et des
autorisations, ainsi que les validations côté serveur.

## Parcours utilisateur

### Projets

L'accueil ouvre sur les ressources et l'activité de l'atelier, puis
la sélection des projets. Le formulaire de création demeure derrière
un panneau repliable pour ne pas imposer sa longueur aux visites
courantes. Le pilotage, les livrables et la recherche sont conservés.

### GitHub

Les quatre onglets sont **Créer un dépôt**, **Protections**,
**Proposer une PR**, **Recette graphique**. À l'ouverture, seul le
premier est affiché ; il est possible de passer à un autre sans
déclencher de requête. Les résultats et confirmations restent liés
au même formulaire et les fonctions sensibles demandent toujours
une approbation exacte.

### Notion

Les six onglets sont **Examiner**, **Modifier**, **Approuver**,
**Texte enrichi**, **Images & tableaux**, **Réception**.

Examiner une page est la première étape logique ; les autres modes
sont disponibles sans réécriture du contenu. Quand un plan multi-blocs
est prêt, l'onglet **Approuver** porte un indicateur discret, sans
déclencher l'écriture ni automatiquement accepter le plan.

## Vérifications et limites

La CI vérifie les pages, les ressources CSS/JS, la conservation des
identifiants des formulaires et leurs contrôles de sécurité. Le job
**`workbench-browser`** ajoute un vrai navigateur Chromium : ouverture
de chaque espace en **1440 × 900 (clair)**, **1366 × 900 (sombre)** et
**390 × 844 (mobile)**, détection des débordements horizontaux,
erreurs JavaScript, navigation par onglets au clavier, bascule de thème
et prévisualisations sans écritures GitHub/Notion. Il conserve jusqu'à
neuf captures d'un **environnement synthétique**, accessibles pendant
sept jours en artefact GitHub Actions.

Ces tests **ne prouvent pas** que le rendu est visuellement excellent
sur le vrai GNOME/Fedora ni qu'un formulaire est optimal pour un
utilisateur réel. Le navigateur s'exécute sur un runner Ubuntu
avec une installation de test sans accès à tes comptes.

Pour la réception visuelle :

- Examiner les trois pages sur le navigateur Fedora en clair et sombre.
- Tester des largeurs 390, 768, 1280 et 1440 px ; vérifier défilement,
  navigation, formulaires, onglets, tableaux et états d'erreur.
- Sur GitHub/Notion, préparer **un plan de test sans l'appliquer**,
  observer les diffs et le panneau d'approbation, puis contrôler
  explicitement les refus.
- Vérifier que la section **installation des outils**, les sous-pages
  Notion et les exercices personnels restent intacts.
- Utiliser `clawfedora-visual-capture` et la
  [grille de revue](validation/VISUAL_RECEPTION_NATIVE.md) pour les
  preuves réelles, sans publier de captures privées.

**Statut :** refonte de code et tests automatisés ; recette
visuelle native sur Fedora et validation réelle des comptes encore
requises. Ne pas présenter ces captures comme déjà produites.
