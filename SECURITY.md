# Sécurité

## Ce que le projet garantit

- Tous les services écoutent sur `127.0.0.1` ; aucun port du pare-feu n'est ouvert.
- SELinux reste en mode `Enforcing` ; aucun script ne le désactive.
- Le modèle est local et aucun service cloud de secours n'est configuré.
- Les rôles ne peuvent ni exécuter de commande, ni écrire directement un fichier, ni ouvrir un navigateur, ni mettre à jour OpenClaw.
- Les secrets et les données de l'atelier (`/srv/openclaw-local`) ne sont jamais dans Git.
- Les versions d'OpenClaw et d'Ollama sont fixées et vérifiées ; rien ne se met à jour seul.

## Ce qu'il ne garantit pas

L'atelier est prévu pour une seule personne sur son propre PC. Il n'est pas conçu pour être exposé sur un réseau ni partagé entre plusieurs utilisateurs. Les sauvegardes ne sont pas chiffrées.

Un texte lu par le modèle (document, page Web) peut chercher à le manipuler. Les consignes lui demandent de traiter ces contenus comme des données, et il n'a aucun outil d'exécution ; cela réduit le risque sans le supprimer.

## Signaler un problème

Ne publie pas de secret ni de donnée privée dans une issue publique. Utilise le signalement privé de vulnérabilité de GitHub sur ce dépôt.
