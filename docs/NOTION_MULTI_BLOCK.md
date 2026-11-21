# Notion — modifications multi-blocs sous revue humaine

[← Modification d'un bloc](NOTION_CONTROLLED_WRITES.md) · [Charte Notion](NOTION_WIKI_DESIGN_SYSTEM.md) · [Recette intégrée](validation/NOTION_GITHUB_ACCEPTANCE.md)

## Fonctionnalité

Le [panneau Notion dans l'atelier](NOTION_DASHBOARD.md) permet de parcourir
ces étapes depuis le navigateur, avec les mêmes validations côté serveur.

`clawfedora-notion-batch` prépare puis applique une **liste exacte de 1 à 5 remplacements
de blocs textuels simples, tous appartenant directement à une seule page existante**.
La commande est réservée à l'opérateur local, distincte de l'import GitHub/Notion
et des outils des agents. **Aucun appel du modèle n'a le droit de l'exécuter.**

Ce n'est pas encore un éditeur complet de wiki : elle ne crée aucune page,
n'ajoute/supprime/déplace aucun bloc, ne remplace pas de page entière et ne touche
pas aux bases de données, vues, sous-pages, images, schémas ou blocs enrichis.
Les liens et le formatage riche font refuser la modification du bloc concerné.
Le quota de cinq changements (7 000 caractères au total) évite les réécritures
massives et aide à relire réellement ce qui sera modifié.

## Sécurité et conservation

- Avant le plan, inventorier **tous les blocs enfants directs** de la page via
  l'API Notion, en refusant les inventaires incomplets et les pages trop grandes.
- Enregistrer l'identité, le type, le nombre d'enfants et le statut archivé
  dans un hash d'inventaire. Le plan contient chaque bloc ciblé, son empreinte
  de contenu et son nouveau texte ; aucun ancien texte n'est conservé dans le plan.
- Afficher un diff avant/après **de chaque bloc**, sans aucune écriture distante.
  Les nouveaux textes et les diffs sont des données **privées locales**.
- Exiger la page exacte, l'empreinte SHA-256 du plan exact, un plan de moins
  de 24 heures et l'option `--apply`.
- Relire **tous** les blocs ciblés et l'inventaire avant d'écrire ; refuser
  les versions décalées. Avant chaque PATCH, recontrôler le bloc et la structure.
- Créer un reçu `ATTEMPTED` avant la première écriture, puis des reçus privés
  par bloc `step-XX.attempted.json` et `step-XX.verified.json`. Aucune
  tentative automatique de reprise, duplication ou rollback distant.

**Limite fondamentale :** l'API Notion ne propose pas de transaction atomique
sur plusieurs blocs ni de mise à jour conditionnelle par version. Une
modification concurrente reste théoriquement possible entre la lecture et
le PATCH. Si la deuxième opération échoue après une première réussite, le lot
est **partiellement appliqué**. Vérifier la page et les reçus, puis créer un
nouveau plan après réconciliation humaine ; ne jamais relancer l'ancien lot.

Le composant ne valide ni l'ergonomie native, ni le rendu clair/sombre,
ni la lecture mobile. Ces contrôles font partie de la recette manuelle.

## Procédure concrète sur une page de test

**1.** Utiliser une page Notion de test à laquelle tes intégrations locales
ont le droit d'accéder. Relever l'ID de la page et les ID précis des blocs
textuels simples à modifier. Ne pas utiliser tes exercices OpsDesk ni la base
personnelle de suivi pour la première recette.

**2.** Préparer un fichier local `/chemin/prive/edits-notion.json` :

```json
{
  "edits": [
    {
      "block_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "text": "Nouveau paragraphe pédagogique revu."
    },
    {
      "block_id": "cccccccccccccccccccccccccccccccc",
      "text": "Titre technique clarifié"
    }
  ]
}
```

Remplacer les identifiants illustratifs par les identifiants **réels**. Le format
est une proposition structurée, et non des instructions exécutables. Les agents
peuvent rédiger les textes, mais l'opérateur reste responsable de choisir les
blocs, comparer le résultat et déclencher les écritures.

**3.** Créer l'aperçu (lecture API réelle, aucune écriture Notion) :

```bash
clawfedora-notion-batch plan \
  --page "IDENTIFIANT_PAGE_REEL" \
  --edits-file "/chemin/prive/edits-notion.json" \
  --output "/chemin/prive/lot-notion.json"
```

Le rapport `BATCH_PREVIEW_ONLY` comporte les diffs et
`manifest_sha256`. Relire chaque suppression/ajout, les changements de
sens et la conservation des sections non ciblées, notamment **l'installation
des outils**. Le plan et les propositions sont locaux : permissions privées
et **aucune synchronisation avec le cloud**.

**4.** Après accord humain sur l'ensemble des changements listés :

```bash
clawfedora-notion-batch apply \
  --plan "/chemin/prive/lot-notion.json" \
  --approve-page "IDENTIFIANT_PAGE_REEL" \
  --approve-manifest "SHA256_DU_PLAN_A_REMPLACER" \
  --apply
```

Le token de lecture est pris dans `NOTION_API_TOKEN`, le token d'écriture
dans `NOTION_WRITE_TOKEN`. Les deux restent **dans l'environnement local**,
pas dans la commande ni dans le dépôt. Utiliser idéalement deux intégrations
Notion distinctes, avec des permissions et pages partagées minimales.

**5.** Inspecter les reçus et ouvrir la page dans Notion. Vérifier les blocs
modifiés, les sous-pages/bases non touchées, les liens, la navigation et le
rendu mobile. La réponse `BATCH_BLOCKS_API_VERIFIED` signifie que les valeurs
des blocs ont été relues après leur PATCH, **pas** que la page entière est
graphiquement certifiée. Ne pas attribuer de progression personnelle ou
une compétence validée sur cette seule base.

## Suite prévue

Le prochain jalon est une **interface locale de préparation et de comparaison**
des changements Notion, soumise aux mêmes contrôles côté serveur que la CLI.
Après cela seulement, étudier une édition de pages plus riches avec conservation
de l'ordre des blocs, images et médias, inventaire des bases et sous-pages,
gestion des échecs et recette graphique native. Les rôles restent au nombre de
sept ; aucun nouvel agent « Notion » n'est nécessaire.
