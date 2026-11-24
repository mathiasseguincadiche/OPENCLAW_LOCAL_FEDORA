# Téléchargements des discussions natives

Les réponses complètes peuvent contenir des documents (Markdown, PDF, DOCX,
ODT, TXT), des fichiers techniques autorisés par le rôle ou des schémas
SVG et draw.io réellement produits par les outils existants.

Le pont récupère sous verrou uniquement les nouveaux reçus de ce tour.
Le serveur associe au message assistant le nom, le format, la taille et
l'empreinte SHA-256 vérifiés de chaque fichier. Le navigateur affiche un
lien local par fichier, sans interpréter les liens ou le HTML du modèle.

Les téléchargements restent disponibles après la fermeture du pont
éphémère et après un redémarrage de l'atelier, tant que la conversation
et ses fichiers/reçus originaux sont conservés. Il ne s'agit pas d'une
seconde archive des fichiers ni d'une garantie de sauvegarde.

## Intégrité et limites

- Même vérification pour le mode classique et le mode SSE.
- Seuls les reçus du rôle enregistré et associés au fil sont admis.
- Le contenu exact des octets servis est revérifié contre le SHA-256
  conservé lors du tour ; une modification ou une disparition refuse le
  téléchargement. Aucun chemin de fichier choisi par le navigateur.
- Le serveur local fournit les octets en pièce jointe ; aucun fichier
  technique n'est exécuté et aucun SVG n'est injecté dans la page.
- Au plus 20 nouveaux reçus, 80 fichiers et 2 Mo par fichier.
- Après interruption, les fichiers éventuellement produits restent dans
  le workspace mais ne sont pas publiés comme résultat d'un tour terminé.
- Les anciens messages restent compatibles, sans reconstruction a
  posteriori des associations manquantes.
- Pas de publication GitHub/Notion, de copie vers le projet ni
  d'approbation implicite. L'interface reste un atelier privé monoposte.

## Recette différée sur Fedora

1. Demander un document à un rôle autorisé en mode classique puis SSE.
2. Télécharger chaque format produit et comparer le SHA-256 avec le reçu.
3. Recharger le fil, redémarrer l'atelier et vérifier les liens.
4. Contrôler qu'un fichier non associé au fil ou modifié est refusé.
5. Interrompre une génération et vérifier l'absence de nouveaux fichiers
   proposés dans le transcript, ainsi que le marqueur d'incertitude.

Les tests automatisés emploient de vrais exports locaux avec un modèle
simulé. La génération par les sept rôles utilisant les deux modèles sur Fedora, la qualité
des livrables et leur pérennité après restauration restent à réceptionner.
