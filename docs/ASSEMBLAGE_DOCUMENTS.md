# Assemblage de documents professionnels en sections

[← Guide](GUIDE.md) · [Exports](PLAN_QUALITE_2026.md) · [Tests Fedora](SMOKE_TEST_WEBUI.md)

La commande humaine `clawfedora-doc-bundle` assemble des sections Markdown UTF-8
déjà rédigées et relues en un livrable cohérent. Elle ne demande aucune
permission supplémentaire à OpenClaw, ne lit aucun secret, ne télécharge rien et
ne lance aucun processus externe.

## Exemple

Préparer `intro.md`, `architecture.md` et `runbook.md` dans un dossier de travail.
Choisir un répertoire de sortie **déjà existant et vide**, puis prévisualiser :

```bash
clawfedora-doc-bundle \
  --part intro.md --part architecture.md --part runbook.md \
  --output-dir ./livrables --name guide-devops

```

Cette commande affiche le plan, les empreintes SHA-256 et les chemins de
livraison **sans écrire de fichier**. Après examen du contenu et accord humain,
ajouter `--apply` pour produire :

- `guide-devops.md` — source éditable assemblée, titres et tableaux conservés ;
- `guide-devops.pdf` — rendu imprimable ;
- `guide-devops.docx` — document éditable ;
- `guide-devops.manifest.json` — empreintes SHA-256 de la source et des exports.

## Garanties et limites

- 1 à 16 sections Markdown, chacune de 12 000 octets maximum ;
  document combiné jusqu'à 60 000 octets.
- Aucun écrasement ; si l'un des noms existe déjà, **rien n'est modifié**.
- Fichiers temporaires privés, publication sans écrasement et nettoyage en cas
  d'erreur d'écriture.
- Références aux sources par nom et SHA-256 ; aucune URL externe chargée.
- Le séparateur entre sections est une règle Markdown horizontale.
- Cette fonction assemble des **sources relues** ; elle ne démontre ni la
  justesse des schémas ni la qualité pédagogique. Vérifier visuellement les
  tableaux, retours à la ligne, blocs de code et pagination PDF/DOCX sur les
  véritables livrables avant soutenance ou livraison.

L'assemblage hors ligne n'augmente pas automatiquement le plafond de production
par appel du modèle (12 000 octets). Pour des dossiers plus longs, rédiger
plusieurs sections, les contrôler puis les assembler.
