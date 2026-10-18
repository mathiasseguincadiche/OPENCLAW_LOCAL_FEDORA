# Fichiers et schémas

[← Guide](../GUIDE.md) · [Rôles et outils](07-roles-et-outils.md) · [Exemple DevOps](../EXEMPLE_PARCOURS_DEVOPS.md)

Demander un document ou une configuration produit un vrai fichier, téléchargeable et modifiable. Le modèle rédige le contenu ; un outil local fabrique le fichier. La conversion tourne sur le processeur, sans service ni abonnement supplémentaire.

## Quels fichiers, par quel rôle

| Rôle | Fichiers |
|---|---|
| Tous | Markdown, texte, PDF et DOCX |
| Architecte | En plus : schémas Draw.io et SVG, ébauches YAML, JSON, Terraform |
| DevOps | En plus : YAML (Ansible, CI, Compose, Kubernetes), Terraform, scripts shell et Python, Dockerfile, modèles Jinja, unités systemd |
| Sécurité | En plus : configurations de droits et de politiques |
| Auditeur | Son propre rapport ; il ne modifie pas les fichiers qu'il relit |

## Dans le chat

Demande le format : « Explique-moi les artefacts d'une CI, puis fournis une fiche en Markdown, PDF
et DOCX. » Les liens de téléchargement s'ajoutent à la réponse. Ils sont valables 24 heures.

Sans projet sélectionné, le chat local accepte jusqu'à quatre petits fichiers texte ou de code totalisant 12 000 octets ; ils servent uniquement à la question courante. Cette voie courte ne prend pas en charge PDF, Office, archives ni images, et elle est toujours refusée en cloud. Les fichiers demeurent dans le stockage Open WebUI jusqu'à leur suppression ou selon sa politique de conservation.

Pour **apporter des sources** à un projet, sélectionne-le puis joins les fichiers avant
`!analyser`. Open WebUI n'indexe pas ces fichiers dans sa propre RAG : un filtre géré transmet
la référence du fichier au pont, qui contrôle son propriétaire, son chemin, sa taille et son nom,
puis l'ajoute à l'ingestion canonique du projet. Les sources sont figées après le début de
l'analyse.

Plan B : copie le fichier dans
`/IA/Openclaw/state/chat-import/inbox/<projet>/` puis tape `!importer`.

## Dans un projet

Précise les formats dans ta demande. Le plan liste alors les fichiers attendus, par exemple :

```text
deliverables/guide/guide.md
deliverables/guide/guide.pdf
deliverables/guide/guide.docx
```

Le Markdown est la source ; le PDF et le DOCX en sont tirés. Pour modifier le document, modifie le Markdown dans le projet : changer le DOCX dans Word ne met pas à jour les autres formats.

## Travail guidé depuis le chat

Quand une tâche guidée attend ta pratique, `!pratique <tâche>` rappelle la consigne. Joins les
fichiers **portant les noms attendus**, puis envoie
`!soumettre <tâche> <ce que tu as fait>`. Ces fichiers sont une soumission humaine, pas de
nouvelles sources : ils passent au spécialiste pour retour, puis aux audits globaux seulement si
les critères sont remplis.

## Limites

- Un appel produit au plus 12 000 octets de contenu et trois exports. Pour un document long, demande-le section par section.
- Le rendu gère titres hiérarchisés, paragraphes, citations, listes, tableaux simples et blocs de code ; le DOCX comprend un pied de page. Les images ne sont pas intégrées. Le rendu est plus lisible mais ne remplace pas une inspection visuelle avant remise.
- Un fichier généré n'est pas un fichier testé. Les fichiers JSON, YAML, Python, TOML et XML sont vérifiés sur leur syntaxe. Terraform, Dockerfile, shell et Jinja sont produits comme du texte : vérifie-les avec leurs propres outils.
- Une image est traitée localement. Elle ne part jamais vers DeepSeek tant que le filtre de confidentialité ne sait pas inspecter son contenu.

## Contrôles disponibles

Les rôles DevOps, sécurité et auditeur peuvent passer un texte dans ShellCheck (Bash), yamllint (YAML), PyMarkdown (Markdown) et Gitleaks (secrets). Ces contrôles regardent la forme. Un YAML valide peut décrire une mauvaise configuration.

Tous les rôles peuvent aussi lire un résumé de résultats de ta CI que tu leur fournis. Ils l'interprètent sans pouvoir vérifier qu'il vient bien de ton pipeline.

## Schémas Draw.io

**À retenir :** le fichier `.drawio` est la **source éditable** du schéma. L'aperçu `.svg` sert à le regarder dans une documentation : changer le SVG ne modifie pas le Draw.io. De la même façon qu'un `.tf` décrit une infrastructure sans l'avoir créée, le diagramme décrit des flux sans prouver qu'ils fonctionnent.

L'architecte génère un fichier `.drawio` que tu ouvres et modifies dans Draw.io : les blocs, les textes et les flèches sont de vrais objets. Un fichier SVG séparé sert d'aperçu pour la documentation.

Un appel produit désormais **une source Draw.io éditable jusqu'à huit vues** : une vue principale et jusqu'à sept vues nommées (par exemple Ensemble, Réseau et Déploiement). Chaque vue garde une limite de **8 blocs et 12 flèches**, pour éviter un graphe illisible. Le SVG et Mermaid n'illustrent **que la vue principale** ; pour retrouver toutes les vues ou éditer des blocs, ouvrir le fichier `.drawio`. Les icônes, groupes, légendes et l'inspection visuelle restent à compléter dans Draw.io.

### Modifier un schéma dans un projet

1. Dans l'étape guidée, clique **Télécharger …drawio**.
2. Ouvre le fichier dans Draw.io, modifie, enregistre.
3. Clique **Remettre le fichier modifié**.
4. Si le plan attend aussi un SVG, réexporte-le depuis Draw.io et remets-le : les deux fichiers ne se synchronisent pas seuls.
5. Explique tes choix, puis soumets pour le retour de l'architecte.

Un [exemple de pipeline](../diagrams/exemple-pipeline.drawio) et son [aperçu](../diagrams/exemple-pipeline.svg) montrent le format produit.
