# Schémas éditables dans Draw.io

Le fichier **`.drawio` est la source du schéma**. Ses blocs, textes et connexions sont des objets natifs modifiables dans Draw.io. Le SVG est un aperçu pour la documentation; le SVG généré ici n’embarque pas la source éditable. Mermaid reste une représentation secondaire pour les anciens usages Markdown.

## Le rôle de l’architecte

L’architecte propose les composants et les flux à partir des besoins, explique les compromis et appelle `clawfedora_diagram`. Le même Qwen local sert aux sept profils, avec un seul appel actif. Le helper transforme une liste de libellés et de connexions en XML et en SVG: aucun modèle de dessin ni serveur supplémentaire.

Une génération couvre **1 à 8 blocs et au plus 12 connexions**. Pour une infrastructure plus grande, prévoir plusieurs petites vues dans le plan: vue générale, réseau, déploiement, stockage. Éviter un fichier énorme et des couches décoratives qui cachent les flux. Les regroupements, annotations et bibliothèques AWS/Azure peuvent ensuite être ajoutés manuellement dans ton Draw.io. Le générateur initial utilise des rectangles simples et des flèches; il ne produit pas des groupes, icônes fournisseurs ou légendes riches.

Le plan doit annoncer les sorties, par exemple `diagrams/design/infra.drawio` et, si utile, `diagrams/design/infra.svg`. L’architecte appelle l’outil avec:

```json
{"nodes":["Git","CI","Image OCI","Kubernetes"],"edges":[[0,1],[1,2],[2,3]]}
```

Le plugin fournit `drawio_reference` et `svg_reference`. L’agent retourne ces références comme valeurs des fichiers attendus, plutôt que réécrire le XML. Le collecteur exige le rôle architecte, un reçu créé pendant cette tâche, l’extension attendue et le hash correspondant. Un schéma n’est jamais une preuve de déploiement.

## Modifier une ébauche dans l’atelier

1. Ouvrir l’étape guidée et cliquer **Télécharger …drawio**. Le brouillon reste privé, hors des livrables publiés.
2. Ouvrir le fichier dans Draw.io Desktop ou dans ton éditeur Draw.io habituel. Pour rester hors ligne, utiliser Desktop déjà installé; aucune installation ni ouverture automatique de site n’est faite par le projet.
3. Modifier les blocs et connexions, enregistrer normalement dans Draw.io, puis expliquer les choix. En mode guidé, l’amorce sert à réfléchir et compléter, pas à livrer une infrastructure déjà faite.
4. Remettre le fichier `.drawio` ou `.xml` avec **Remettre le fichier modifié**. Les sauvegardes compressées habituelles de Draw.io sont acceptées: le serveur les convertit localement, avec décompression bornée, en XML lisible avant le retour pédagogique. Le chemin approuvé du livrable reste `.drawio`.
5. Si le plan attend aussi un SVG, le réexporter depuis Draw.io et le remettre dans son champ. **Les deux fichiers ne sont pas synchronisés automatiquement**, et le SVG initial devient obsolète après édition.
6. Donner ton raisonnement et les limites observées, puis soumettre. L’architecte relit le fichier actuel et les critères; les dépendants attendent ce retour avant publication.

Le formulaire conserve une vue du texte sous «Voir le contenu du fichier», sans demander de manipuler du XML pour une modification habituelle. La soumission entière reste limitée à 60 Ko, avant et après décompression. Le fichier conservé est en XML non compressé: au plus 8 pages et 256 cellules par page, identifiants distincts, géométries et connexions valides. Les DTD, entités XML, sauvegardes corrompues et décompressions excessives sont refusées. Ce contrôle vérifie la structure du fichier, pas la qualité d’une architecture ni la sécurité d’une infrastructure. Un aperçu remis par l’apprenant n’est pas automatiquement comparé visuellement à la source.

## Mettre à jour un projet déjà publié

Passer par **Demander une modification cohérente du projet**, choisir la tâche d’architecture et consulter son impact. Après approbation, le moteur archive les anciennes contributions et reprend les tâches dépendantes, dont la documentation et les audits. Remettre le schéma modifié dans la nouvelle étape guidée. Modifier un fichier dans Draw.io sur ton PC ne déclenche pas cette reprise à lui seul.

## Pourquoi cette intégration légère

Le plugin métier existant suffit: export natif Draw.io, aperçu local, références vérifiées, téléchargement et reprise de fichier. Le petit parseur Python defusedxml 0.7.1 protège la lecture des XML importés, y compris après décompression. Graphviz n’est plus requis par cet outil et le bootstrap ne l’installe plus; une ancienne installation n’est pas désinstallée automatiquement. L’éditeur reste un outil de l’apprenant. Aucun diagramme n’est envoyé automatiquement sur Internet.

Draw.io propose aussi un [serveur MCP et des plugins officiels](https://www.drawio.com/docs/reference/diagram-generation/). Ils peuvent devenir utiles pour piloter l’éditeur ou exporter avec sa CLI. Ils ne sont pas intégrés ici: leur ajout demande une vérification de compatibilité OpenClaw, de droits et d’usage réel. Le plugin local conserve le périmètre actuel et évite un service permanent supplémentaire.

Un [exemple de pipeline éditable](diagrams/exemple-pipeline.drawio) et son [aperçu SVG](diagrams/exemple-pipeline.svg) montrent le format livré. C’est une illustration, pas une infrastructure installée ou une recommandation d’utiliser tous ces composants à la fois.

Références officielles: [structure XML et génération](https://www.drawio.com/docs/reference/diagram-generation/), [formats de sauvegarde](https://www.drawio.com/docs/manual/editor/save-file-formats/), [export XML non compressé](https://www.drawio.com/docs/manual/export/export-to-xml/).
