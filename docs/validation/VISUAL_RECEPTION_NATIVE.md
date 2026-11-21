# Réception visuelle native — Notion, GitHub et panneaux Fedora

[← Réception intégrée](NOTION_GITHUB_ACCEPTANCE.md) · [Panneau Notion](../NOTION_DASHBOARD.md) · [Panneau GitHub](../GITHUB_CHAT_DASHBOARD.md)

## Vérification navigateur automatisée préalable

Le job GitHub Actions `workbench-browser` exécute Chromium sur les
**trois panneaux locaux** avec une instance de test et des données
entièrement synthétiques. Il produit des captures bureau clair/sombre
et mobile dans l'artefact `workbench-browser-synthetic-screenshots`
(rétention sept jours). Le test échoue en cas d'exception JavaScript,
débordement horizontal de page, onglet non fonctionnel, bascule de
thème cassée ou aperçu sensible qui se publie seul.

**Ces captures ne concernent pas le compte Notion/GitHub authentifié,
ne sont pas prises sur Fedora et ne prouvent pas la qualité esthétique.**
La réception humaine sur les pages réelles décrite ci-dessous reste
obligatoire.

## Objectif et limites

Le nouveau couple **`clawfedora-visual-capture`** /
**`clawfedora-visual-review`** fournit un chemin reproductible vers de
**véritables captures du navigateur**, sans publier les informations capturées.

Il sépare quatre faits qui ne doivent jamais être confondus :

| Preuve | Ce qu'elle démontre | Ce qu'elle ne démontre pas |
| --- | --- | --- |
| Tests Python / CI GitHub | Les cas simulés et contrats automatisés passent | Une page réelle est agréable ou correcte à lire |
| Capture Playwright | Un navigateur Chromium a affiché une cible et produit des PNG | Tous les contenus et interactions sont parfaits |
| Mesures DOM | Largeur du document, débordement horizontal, titres, images sans alt | Contraste perçu, utilité, exactitude éditoriale |
| Revue explicite | L'opérateur **déclare** avoir ouvert et évalué les critères | Une certification automatique indépendante |

**Une PR verte ne remplace pas cette réception.** La CI vérifie les refus,
l'intégrité du protocole et les manifestes synthétiques : elle n'ouvre ni ton
compte Notion ni ton PC personnel. Les outils ne modifient ni les pages Notion,
ni les dépôts GitHub et n'envoient aucune capture à un service externe.

## Prérequis sur le PC Fedora

- Atelier à jour, installation réelle et session Fedora 45 fonctionnelles.
- Pour les panneaux : serveur local démarré sur `127.0.0.1:18890`.
- Pour GitHub : README réel visible et, si privé, connexion interactive manuelle.
- Pour Notion : page accessible avec ton compte ; ouvrir le navigateur temporaire
  en mode **interactif** et s'authentifier **manuellement**, jamais via un secret
  collé dans la CLI, la configuration Git ou un prompt.
- Dossier de captures **privé et hors dépôt Git**.

La capture est un supplément opt-in, pour ne pas imposer les binaires
Chromium/Playwright à toutes les installations. Depuis la racine du dépôt,
dans un environnement Python Fedora compatible :

```bash
# Installer l'option visuelle épinglée ; ne pas remplacer les dépendances
# de l'atelier par une installation non isolée.
python -m pip install -e '.[visual]'

# Installer le navigateur utilisé par l'option Playwright.
python -m playwright install chromium

# Dossier d'évidence hors de Git, accessible au seul utilisateur.
install -d -m 700 "$HOME/.local/state/openclaw-visual"
```

Playwright est **épinglé** dans `pyproject.toml` ; vérifier
la compatibilité du Chromium empaqueté avec Fedora et noter
sa version dans le rapport de réception du PC.

## Capturer les quatre périmètres

Toutes les commandes sont **en lecture seule des sites**. Sans
`--capture`, elles ne lancent même pas le navigateur.

```bash
PROOFS="$HOME/.local/state/openclaw-visual"

# 1. Panneau local Notion : interface, tableaux, encadrés et approbations.
clawfedora-visual-capture \
  --kind local-notion \
  --url http://127.0.0.1:18890/notion.html \
  --output-dir "$PROOFS" --capture

# 2. Panneau local GitHub : dépôt, workflow et validation humaine.
clawfedora-visual-capture \
  --kind local-github \
  --url http://127.0.0.1:18890/github.html \
  --output-dir "$PROOFS" --capture

# 3. README réel GitHub : remplacer par le dépôt du projet à réceptionner.
clawfedora-visual-capture \
  --kind github-readme \
  --url https://github.com/PROPRIETAIRE/NOM_DEPOT \
  --output-dir "$PROOFS" --capture

# 4. Page réelle Notion : remplacer par une page de test et se connecter
# manuellement dans le navigateur temporaire. Captures CONFIDENTIELLES.
clawfedora-visual-capture \
  --kind notion-page \
  --url https://app.notion.com/p/IDENTIFIANT_PAGE_DE_TEST \
  --output-dir "$PROOFS" --interactive --allow-private --capture
```

Si GitHub est privé, utiliser `--interactive` pour ouvrir la session
de manière manuelle. Ne jamais sauvegarder de `storage_state`, cookies,
sessions, mots de passe, fichiers de jetons ou variables d'environnement
dans les preuves. Le navigateur utilise une **session temporaire** et
n'exporte aucune authentification.

Le programme produit pour chaque cible un dossier privé distinct
`capture-<identifiant>/` et un `manifest.json`. Chaque profil
**desktop clair**, **desktop sombre** et **largeur mobile** est rendu
à son format propre ; chaque vue donne une à trois captures
haut/milieu/bas selon la hauteur du document. Les longues pages ne
sont donc pas nécessairement capturées en totalité.

**Attention :** la préférence clair/sombre demandée au navigateur
n'oblige pas GitHub ou Notion à changer de thème. L'opérateur doit
vérifier le thème **réellement affiché**. La largeur 390 px simule
un viewport mobile, pas un appareil mobile complet. Ces différences
doivent être notées comme limites, pas masquées.

## Revue explicite et reçu

Dans chaque dossier `capture-…`, construire d'abord une grille
complète initialement **non évaluée** :

```bash
clawfedora-visual-review \
  --manifest "/chemin/prive/capture-ID/manifest.json" \
  --template-out "/chemin/prive/capture-ID/observations.json"
```

Ouvrir les captures **et le site réel**. Modifier le fichier
`observations.json` privé : remplacer `inspected_live_site: false`
par `true` uniquement après l'avoir réellement examiné ; attribuer
à chacun des critères `PASS`, `FAIL` ou `NOT_EVALUATED`.

Les critères varient selon la cible. Au minimum, évaluer navigation,
lisibilité, exactitude du contenu, liens, thème, mise en page mobile,
absence de chevauchements, et :

- **Notion** : conservation de la section **installation des outils**,
  sous-pages, suivi, encadrés, tableaux et images ;
- **GitHub** : lisibilité du README, schémas techniques et de
  présentation, légendes, navigation, protections de publication ;
- **Panneaux locaux** : formulaires d'autorisation, états, erreurs
  de validation et disponibilité des actions.

Ne jamais marquer `PASS` sur un critère non examiné. Si la mesure
automatique détecte un débordement horizontal du document, le verdict
est `OPERATOR_REVIEW_FAILED` même si toutes les cases humaines
ont été mises à `PASS`.

```bash
# Aperçu en lecture seule, sans création de reçu.
clawfedora-visual-review \
  --manifest "/chemin/prive/capture-ID/manifest.json" \
  --review "/chemin/prive/capture-ID/observations.json"

# Enregistrer le reçu privé après la revue effectivement réalisée.
clawfedora-visual-review \
  --manifest "/chemin/prive/capture-ID/manifest.json" \
  --review "/chemin/prive/capture-ID/observations.json" \
  --output "/chemin/prive/capture-ID/reception.json" --apply
```

Un reçu dit **`OPERATOR_REVIEW_REPORTED_PASS`** si toutes les
observations sont positives et qu'aucun débordement horizontal
n'est détecté. Il ne dit jamais « certifié par l'IA ».
Si une capture a été modifiée depuis le manifeste, le reçu est
**refusé**.

## Contrôles métier à faire sur les vraies pages

**Notion :** comparer l'accueil, une fiche de cours, la préparation
de l'environnement et les exercices ; ouvrir les liens ; vérifier
la présence de la section d'installation, des tableaux et images
réellement attendus ; constater que ni la progression privée ni
les sous-pages ne sont altérées. Vérifier également les SVG
publiés par rapport à leurs sources `.drawio`.

**GitHub :** ouvrir le vrai README dans la vue GitHub, tester les
liens relatifs, vérifier le diagramme de présentation distinct du
diagramme technique, les preuves de CI et la lecture sur mobile.
Aucune capture n'autorise automatiquement une publication ou une
fusion.

**Fedora :** répéter la capture sur ton matériel réel,
enregistrer le SHA déployé et la date, puis exécuter séparément
`./menu.sh --action quick-check`, les tests des sept agents, le
workflow d'un projet témoin et les essais de sauvegarde/restauration
décrits dans [la recette générale](NOTION_GITHUB_ACCEPTANCE.md).

Conserver les preuves privées dans `$HOME/.local/state/openclaw-visual`.
**Ne pas les committer, les partager publiquement ni les envoyer à
un modèle cloud.** La recette native reste ouverte tant que les
actions ci-dessus n'ont pas réellement été exécutées.
