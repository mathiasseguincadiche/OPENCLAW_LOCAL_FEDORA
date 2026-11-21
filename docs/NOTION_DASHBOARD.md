# Panneau Notion local — prévisualiser et approuver les révisions

[← Accueil documentation](README.md) · [Édition multi-blocs](NOTION_MULTI_BLOCK.md) · [GitHub dans l'atelier](GITHUB_CHAT_DASHBOARD.md) · [Réception réelle](validation/NOTION_GITHUB_ACCEPTANCE.md)

## Accès

L'atelier Projets expose, depuis la même interface locale, le panneau
**`http://127.0.0.1:18890/notion.html`**. Il est également accessible
par le lien **Notion : wiki et révisions** de l'accueil.

C'est une interface **locale et explicite** de l'éditeur
`clawfedora-notion-batch`. Elle ne lit pas les notes Notion sans que
l'opérateur fournisse un ID de page et déclenche l'action correspondante.
Elle ne transmet pas les jetons au navigateur ni à un modèle.

## Ce que l'interface permet

1. **Examiner** une page existante explicitement choisie : inventaire en
   lecture seule, résumés courts des blocs textuels, étiquette des blocs
   protégés (enfants, sous-pages, bases, images, blocs spéciaux).
2. **Composer** une proposition contenant entre un et cinq corrections
   textuelles, à partir de textes préparés ou relus par les sept rôles.
   Le texte est collé localement ; il ne vient pas d'une commande
   autonome de l'IA.
3. **Prévisualiser** un diff pour chaque bloc et l'empreinte SHA-256 du
   plan. L'inventaire et les valeurs actuelles sont relus par le moteur
   avant de construire le plan.
4. **Approuver** exactement la page et l'empreinte proposées, avec une
   case d'autorisation humaine distincte. Le serveur ne reçoit aucune
   autorisation implicite de l'IA.
5. **Vérifier** les réponses de l'API Notion puis contrôler manuellement
   le résultat réel dans Notion, y compris les sous-pages, l'installation
   des outils et la lisibilité sur bureau/mobile.

Le formulaire ne permet **aucune** suppression, insertion, déplacement ou
création de page. La fonctionnalité est limitée aux blocs simples d'une
même page, à la configuration de la PR dédiée. Les blocs avec formatage
riche ou liens ne sont pas admissibles même s'ils apparaissent comme
candidats dans l'inventaire : le moteur Python les refuse au moment du
plan ou de la vérification avant l'écriture.

## Où se trouvent les données et les autorisations ?

Les identifiants de pages et de blocs ne servent qu'aux appels locaux de
l'opérateur. Le serveur prend ses accès Notion dans l'environnement du
processus Fedora : **`NOTION_API_TOKEN` en lecture** et
**`NOTION_WRITE_TOKEN` en écriture**. Les secrets ne doivent jamais
être collés dans un champ du navigateur, une conversation, un README
ou un outil GitHub. Partager uniquement la **page de test** avec les
intégrations adéquates pour la première recette.

Le plan est créé dans le dossier privé
`<runtime>/state/notion-ui/<identifiant-aléatoire>.plan.json`
(`0600`, dossier `0700`), et le navigateur ne reçoit qu'un identifiant
opaque, les différences et l'empreinte. Les reçus `ATTEMPTED` et
`step-NN.verified` ne sont pas des captures du rendu natif.

Le serveur impose une origine identique au panneau
(`http://127.0.0.1:18890`, ou le port local configuré), vérifie l'hôte,
refuse les requêtes JSON trop volumineuses et **n'autorise pas les chemins
de fichiers envoyés par le navigateur**. Les opérations sont soumises
au même verrou que les autres actions sensibles de l'atelier.

## Recette recommandée

- D'abord sur une **page Notion de test** créée pour l'occasion, pas
  sur le wiki OpsDesk ni sur des exercices personnels.
- Préparer deux corrections simples, inspecter les diffs et vérifier
  l'empreinte. Une lecture ou une prévisualisation doit produire
  **zéro écriture distante**.
- Essayer une fausse empreinte : l'écriture doit être refusée.
- Tester avec l'approbation exacte et vérifier la page dans Notion.
- Modifier un bloc dans Notion entre l'aperçu et l'approbation : l'API
  doit refuser le lot, sans écraser l'édition tierce.
- En cas d'échec après un premier PATCH, **ne pas relancer le lot** :
  examiner Notion et les reçus avant toute nouvelle proposition.

La CI du dépôt vérifie des scénarios synthétiques (origine HTTP,
approbation, conflits et anti-rejeu). Elle ne certifie ni la connexion
réelle à Notion, ni l'affichage GNOME, ni le navigateur sur Fedora,
ni les compétences acquises pendant les exercices. Ces preuves
appartiennent à la [campagne de réception](validation/NOTION_GITHUB_ACCEPTANCE.md).

## Étapes restant à développer

- Import assisté de **propositions validées des agents** depuis les
  livrables d'un projet sélectionné (l'éditeur courant attend
  du texte saisi/collé par l'opérateur).
- Gestion des sections enrichies, callouts, tableaux, médias, schémas et
  ajout contrôlé de pages.
- Prévisualisation visuelle complète des blocs comme ils apparaîtront
  réellement dans Notion, et preuve native bureau/mobile.

Ces capacités ne doivent pas être annoncées comme fonctionnelles tant
qu'elles ne sont pas codées et qualifiées.
