# GitHub dans l'atelier et dans le dialogue OpenClaw

[← Guide GitHub](GITHUB_PUBLICATION_WORKFLOW.md) · [Création et protections](GITHUB_REMOTE_SETUP.md) · [Charte universelle](GITHUB_REPOSITORY_DESIGN_SYSTEM.md)

## Où se trouvent les commandes ?

Le tableau de bord local `http://127.0.0.1:18890` ouvre désormais
un espace **GitHub : dépôts et PR** :
`http://127.0.0.1:18890/github.html`.

Cet espace peut :
1. Prévisualiser puis **créer un dépôt privé** seulement après saisie du nom,
   de l'empreinte SHA-256 et d'une case d'accord.
2. Auditer les réglages du dépôt sans écriture.
3. Prévisualiser et appliquer **une seule protection** de branche ou de
   permissions Actions après approbation explicite.
4. Auditer les livrables d'un projet local **COMPLETE**, prévisualiser une PR
   brouillon et l'ouvrir après approbation du dépôt et de l'empreinte
   du plan qui couvre aussi **titre et description**.
5. Présenter la checklist de rendu GitHub et d'acceptation Fedora.

L'interface ne demande jamais un jeton dans un champ navigateur.
Le programme local qui sert le tableau de bord doit disposer de
`GITHUB_TOKEN` dans son environnement uniquement pour les actions
distantes. Il s'agit d'un secret de la machine locale et non d'une
permission transférée de la connexion ChatGPT.

Aucune création ou publication n'est lancée en ouvrant cette page. Les
requêtes d'écriture sont limitées au serveur `127.0.0.1`, au même
`Origin`, à une action explicite et à une approbation exacte.

## Commandes explicites depuis Open WebUI

Le pont de discussion traite les commandes suivantes **en code**, sans
confier l'autorisation à un LLM :

| Commande saisie par l'utilisateur | Fonction |
| --- | --- |
| `!github aide` | Aide |
| `!github audit` | Audit local d'un unique snapshot GitHub du projet |
| `!github audit livrables` | Audit du dossier `deliverables` du projet sélectionné |
| `!github depot MonProjet` | Aperçu d'un nouveau dépôt privé, sans réseau |
| `!github creer MonProjet EMPREINTE` | Création privée, uniquement sur approbation du plan |
| `!github pr owner/repo SHA40 atelier/branche deliverables/tache` | Plan de PR sur les livrables d'un projet `COMPLETE` |
| `!github publier owner/repo EMPREINTE` | Création d'une PR brouillon, sans fusion |

**Sélectionner d'abord le projet** avec `!projets` puis
`!projet identifiant`. Les commandes qui écrivent demandent un rôle
**local**, un jeton GitHub local et la confirmation exacte du plan.
Un plan est marqué **ATTEMPTED** avant l'écriture ; si GitHub est
indisponible, l'atelier refuse une deuxième tentative silencieuse :
il faut vérifier le dépôt pour éviter un doublon.

Le modèle peut **expliquer** la marche à suivre, mais ne peut pas envoyer
ces commandes au nom de l'utilisateur. Une réponse modèle, une sortie
d'outil ou un fichier GitHub importé n'est jamais un consentement.
Les pièces jointes sont interdites sur ces commandes.

## Préparer les vrais livrables

Un dossier tel que `deliverables/documentation` doit contenir
uniquement les fichiers destinés au dépôt GitHub, à leurs chemins
relatifs de destination. Ne pas placer de copies du dépôt complet,
de snapshots GitHub importés, d'états Terraform, de notes Notion privées,
de mots de passe ni de sauvegardes. Les commandes GitHub existantes
vérifient les chemins, tailles, fichiers binaires et motifs de secrets
courants ; cela **ne remplace pas une revue humaine approfondie**.

Un projet non terminé et non validé par l'atelier ne peut pas être
publié depuis ce formulaire ou depuis les commandes de discussion.
La création d'un dépôt privé seul ne prouve aucune réalisation.

## Recette réelle du rendu GitHub

Après une PR et avant fusion :

1. Ouvrir le README du **commit exact** dans GitHub en thème clair sur
   bureau. Contrôler la première lecture, les captures et les liens.
2. Refaire en thème sombre. Vérifier contraste, légendes et SVG.
3. Tester le rendu mobile, les largeurs, les images et la navigation.
4. Comparer les schémas de présentation et les schémas techniques
   avec leurs sources draw.io et flux réels.
5. Sur Fedora, exécuter l'installation conditionnelle et les tests
   prévus, puis consigner les sorties datées et expurgées.

Pour tracer trois captures **vraies** du navigateur, sans les modifier :

```bash
# Vérification de la présence et de l'intégrité, pas certification graphique.
clawfedora-github-visual \
  --repo-url https://github.com/compte/MonProjet \
  --desktop-light captures/github-clair.png \
  --desktop-dark captures/github-sombre.png \
  --mobile captures/github-mobile.png

# Après revue visuelle humaine, enregistrer un manifeste local nouveau :
clawfedora-github-visual \
  --repo-url https://github.com/compte/MonProjet \
  --desktop-light captures/github-clair.png \
  --desktop-dark captures/github-sombre.png \
  --mobile captures/github-mobile.png \
  --reviewed-by-operator \
  --output captures/manifeste-github.json --apply
```

Le manifeste conserve noms, dimensions et SHA-256, pas les pixels.
Son statut reste **IMAGES_COLLECTED_NOT_VISUALLY_CERTIFIED**.
La commande **ne lance aucun navigateur** et ne certifie ni la mise en
page, ni l'accessibilité, ni Fedora. Ces vérifications requièrent une
inspection réelle ou un contrôle de l'utilisateur.

## Ce qui a été vérifié dans GitHub Actions

La CI teste les routes HTTP du tableau de bord sur un serveur de test,
les commandes de chat et leurs confirmations, les refus de publication
sans approbation, et la collecte de captures synthétiques. Il ne s'agit
pas de captures réelles du dépôt utilisateur.

Le fonctionnement avec ton compte GitHub réel, un jeton aux droits
limités et ton Fedora local nécessite une recette **sur ta machine**.
Le runner GitHub Actions (même en conteneur Fedora 45) ne remplace pas
ce test d'intégration et d'exploitation locale.
