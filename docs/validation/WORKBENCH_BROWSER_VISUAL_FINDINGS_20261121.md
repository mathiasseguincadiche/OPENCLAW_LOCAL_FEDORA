# Revue des captures du workbench — 21 novembre 2026

[← Design system](../WORKBENCH_UI_DESIGN.md) · [Réception native](VISUAL_RECEPTION_NATIVE.md)

## Preuves réellement consultées

Captures **synthétiques Chromium** du job GitHub Actions `workbench-browser`
de la PR #221, exécution [44950863525](https://github.com/mathiasseguincadiche/OPENCLAW_LOCAL_FEDORA/actions/runs/44950863525),
artefact `workbench-browser-synthetic-screenshots` (durée de vie : 7 jours).

Les **neuf images** ont été consultées ensemble : 3 pages
(Projets, GitHub et Notion) sur 3 formats (1440 px clair,
1366 px sombre et 390 px clair). Ce sont de vrais pixels Chromium
sur Ubuntu CI, mais **pas** des captures du PC Fedora ni de
l'authentification Notion/GitHub de l'utilisateur.

## Constats

| Point | Observation | Traitement |
| --- | --- | --- |
| Navigation bureau | Rail constant, état actif visible, en-têtes et cartes alignés | Conserver la base |
| Modes clair et sombre | Deux palettes présentes sur les 3 pages dans les captures | Vérifier manuellement les contrastes sur Fedora |
| Mobile 390 px | Rail réduit à 3 icônes : les libellés textuels sont masqués en CSS, sans nom ARIA explicite dans le code initial | **Corrigé** : chaque lien a un nom accessible et un intitulé au survol |
| Notion mobile | Les 6 onglets dépassent la largeur et seuls les 3 premiers sont visibles sans défilement horizontal ; la possibilité d'accéder aux autres n'est pas assez explicite | **Corrigé** : commandes Précédent/Suivant, compteur d'étapes et suivi de l'onglet actif |
| GitHub mobile | Les 4 onglets occupent également une barre déroulante peu intuitive | **Corrigé** par les mêmes commandes |
| Clavier | La navigation latérale précède le contenu principal, sans raccourci d'évitement | **Corrigé** : lien Aller au contenu principal, cible focalisable |
| Sécurité | Les formulaires d'approbation sont masqués tant que leur plan n'est pas prêt | Contrôles inchangés ; tests navigateur dédiés |
| Débordement horizontal | Aucun débordement global signalé par les 14 tests Chromium de la PR #221 | Conserver la surveillance du document |

## Réception encore nécessaire

Les correctifs sont vérifiables en Chromium de CI, mais la
revue graphique ne vaut pas certification esthétique :
- ouvrir les écrans sous Fedora 45 / GNOME 51 ;
- vérifier les modes clair/sombre et l'ergonomie tactile
  aux largeurs 390, 768, 1280 et 1440 px ;
- tester tous les onglets, formulaires longs, textes enrichis,
  tableaux, erreurs et la lecture au clavier/lecteur d'écran ;
- distinguer les contenus de test des pages Notion et dépôts GitHub réels ;
- conserver les exercices personnels et la section **installation des outils**.

**Verdict :** corrections mobiles et d'accessibilité justifiées
par la revue, sans déclaration de `RENDU_VISUEL_VERIFIE`
sur le PC Fedora.
