# Sécurité

## Ce que le projet garantit

- Tous les services écoutent sur `127.0.0.1` ; aucun port du pare-feu n'est ouvert.
- SELinux reste en mode `Enforcing` ; aucun script ne le désactive.
- Le modèle est local par défaut. Le cloud (DeepSeek V4.1 Flash par OpenRouter) est **désactivé tant que tu ne l'actives pas**, et il ne s'active que si le filtre de confidentialité et le contrôle du budget fonctionnent ensemble. Aucun repli automatique du local vers le cloud.
- Quand le cloud est actif, seule la passerelle locale (`127.0.0.1:18892`) connaît ta clé OpenRouter et sort vers Internet : elle filtre tout ce qui part (historique et résultats d'outils compris), compte chaque appel facturé et refuse au plafond de 25 € réels par mois. La clé est dans un fichier à droits 0600, jamais dans Git, les journaux, la configuration d'OpenClaw ni les sauvegardes.
- Un projet de l'atelier n'utilise le cloud qu'avec ton accord explicite, lié à ses sources ; en cas de blocage, il se met en pause au lieu de basculer en local sans te le dire.
- Les rôles ne peuvent ni exécuter de commande, ni écrire directement un fichier, ni ouvrir un navigateur, ni mettre à jour OpenClaw.
- Les secrets et les données de l'atelier (`/srv/openclaw-local`) ne sont jamais dans Git.
- Les versions d'OpenClaw et d'Ollama sont fixées et vérifiées ; rien ne se met à jour seul.

## Ce qu'il ne garantit pas

L'atelier est prévu pour une seule personne sur son propre PC. Il n'est pas conçu pour être exposé sur un réseau ni partagé entre plusieurs utilisateurs. Les sauvegardes ne sont pas chiffrées (elles n'emportent pas la clé OpenRouter, mais gardent ta liste de termes sensibles et le journal du budget).

Le filtre de confidentialité arrête les secrets (clés, jetons, mots de passe, identifiants réels), pas un contenu confidentiel qui n'en a pas l'allure : un nom de serveur interne ou la configuration d'un employeur peuvent partir au cloud si tu choisis le modèle cloud. Pour ces contenus, reste en local. Le fournisseur reçoit ce que le filtre laisse passer, avec `data_collection: deny` demandé à OpenRouter ; ce réglage n'est pas une garantie contractuelle.

Un texte lu par le modèle (document, page Web) peut chercher à le manipuler. Les consignes lui demandent de traiter ces contenus comme des données, et il n'a aucun outil d'exécution ; cela réduit le risque sans le supprimer.

## Signaler un problème

Ne publie pas de secret ni de donnée privée dans une issue publique. Utilise le signalement privé de vulnérabilité de GitHub sur ce dépôt.
