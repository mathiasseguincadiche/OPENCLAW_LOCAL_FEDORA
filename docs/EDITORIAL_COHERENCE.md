# Cohérence documentaire GitHub / Notion

[Charte Premium](EDITORIAL_PREMIUM_V2.md) · [Revue éditoriale](EDITORIAL_CYCLE.md)

GitHub décrit le projet technique ; Notion peut approfondir les décisions,
l'apprentissage et les détails privés. Ils ne doivent pas être des copies
intégrales. Le contrôle compare des références factuelles explicitement
déclarées dans des instantanés locaux, et prépare une file de revue.

## Références à maintenir

Choisir les faits qui doivent rester identiques entre les supports :
révision d'architecture, version d'un outil, décision ADR, statut de
qualification, identifiant de preuve ou référence d'identité graphique.
Les distinguer des détails qui ne doivent pas figurer dans un espace public.
Utiliser des identifiants neutres, sans secret, dans les clés et noms de source.

Une ligne de texte simple dans un paragraphe Notion ou dans Markdown suffit :

~~~text
Référence éditoriale [architecture.revision] : V3
Référence éditoriale [qualification.lab] : à réaliser
~~~

Ce registre est un complément court, pas une obligation de répéter toute
la documentation. Les exemples dans les blocs de code sont ignorés.
Ne jamais mettre de mot de passe ou de jeton dans ces lignes.

## Sélectionner les sources

Employer les instantanés issus de l'importeur existant : GitHub épinglé
sur un commit et export Notion privé horodaté. L'opérateur sélectionne
jusqu'à 24 fichiers Markdown et leurs SHA-256, dans un dossier local
commun (par exemple l'intake du projet). Le fichier JSON de sélection
est privé et peut être préparé à partir des empreintes locales.
GitHub peut être classé public ou private ; Notion reste private.
Les classifications ne prouvent pas les permissions de partage réelles.

Exemple de schéma (identifiants et empreintes fictifs à remplacer) :

~~~json
{
  "schema": 1,
  "sources": [
    {
      "id": "readme",
      "support": "github",
      "visibility": "public",
      "snapshot": "GitHub-example-atlas-aaaaaaaaaaaa",
      "path": "README.md",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    },
    {
      "id": "wiki",
      "support": "notion",
      "visibility": "private",
      "snapshot": "Notion-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "path": "page-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.md",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "revision": "2026-11-25T20:00:00Z"
    }
  ],
  "facts": {
    "architecture.revision": "shared",
    "qualification.lab": "shared",
    "lab.internal_reference": "private"
  }
}
~~~

La révision GitHub correspond au commit du fichier de provenance.
La révision Notion correspond à son champ captured_at.
Pour une nouvelle capture, préparer une nouvelle sélection ; le contrôle
ne rafraîchit pas les sources, ni ne change l'intake scellé.

~~~bash
python -m clawfedora.editorial_coherence --root DOSSIER_LOCAL \
  --manifest coherence.json
~~~

## Interpréter

| Signal | Action |
| --- | --- |
| REFERENCE_DIVERGENCE | Relire les deux sources et déterminer la décision actuelle |
| SHARED_REFERENCE_MISSING | Vérifier la couverture sur chaque support |
| PRIVATE_REFERENCE_MISSING | Vérifier la sélection privée |
| PRIVATE_FACT_EXPOSURE | Examiner la localisation, retirer la donnée du support public si nécessaire |
| UNCLASSIFIED_FACT | Classer explicitement la référence |
| REPEATED_REFERENCE | Éliminer l'ambiguïté dans un document |

Les rapports ne reproduisent ni valeurs, ni extraits, ni chemins privés :
uniquement identifiants neutres, numéros de lignes et empreintes de sources.
Les valeurs privées explicites de 12 caractères ou plus sont aussi cherchées
littéralement, sans tenir compte de la casse, dans les sources publiques
sélectionnées. Une correspondance peut être fortuite. Un marqueur privé
dans un document public est signalé quelle que soit la longueur de sa valeur.

Codes de sortie : 0 références déclarées alignées, 1 revue nécessaire,
2 entrée refusée. Un résultat aligné ne certifie ni vérité technique, ni
rendu graphique, ni preuve, ni exhaustivité. Les formulations libres et
les liens, les médias et les données des bases Notion ne sont pas comparés.
Utiliser Gitleaks et les revues de sécurité existantes pour les secrets,
et les outils de recette visuelle pour les compositions.
Le module est opérateur, local et sans écriture distante. Toute correction
GitHub ou Notion relève du processus d'approbation existant.
